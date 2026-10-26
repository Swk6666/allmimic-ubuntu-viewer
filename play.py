#!/usr/bin/env python3
"""Play an AllMimic policy in native CPU MuJoCo; no CUDA or mjlab required."""

import argparse
import json
import os
from pathlib import Path
import queue
import sys
import time

HERE = Path(__file__).resolve().parent
for variable, directory in {
    'XDG_CACHE_HOME': 'cache', 'MPLCONFIGDIR': 'config/matplotlib',
    'TORCH_HOME': 'cache/torch', 'TORCHINDUCTOR_CACHE_DIR': 'cache/torchinductor',
}.items():
    os.environ[variable] = str(HERE / directory)

import mujoco
import numpy as np
import torch

from allmimic import networks
from allmimic.kinematics import FastTreeKinematics
from allmimic.motion_lib import MotionLibrary
from allmimic.networks import Policy
from allmimic.rotations import quat_normalize, quat_to_mat
from allmimic.task import GOAL_FRAME_DIM, OBS_DIM, Task, task_cfg


class Player:
    def __init__(self, clip, policy_path):
        self.ck = torch.load(policy_path, map_location='cpu', weights_only=True)
        self.meta = json.loads((HERE / 'robot_metadata.json').read_text())
        self.model = mujoco.MjModel.from_xml_path(str(HERE / 'robot/scene.xml'))
        for key, value in self.meta['mujoco_options'].items():
            setattr(self.model.opt, key, value)
        self.model.geom_friction[self.meta['foot_geoms'], 0] = 1.0
        self.data = mujoco.MjData(self.model)
        self.cfg = task_cfg(self.ck['cfg'], train=False)
        self.lib = MotionLibrary(str(HERE / 'motions.npz'), 'cpu', keep={clip})
        if self.lib.num_clips != 1:
            raise ValueError(f'Unknown motion {clip!r}; run with --list')
        self.kin = FastTreeKinematics(self.model, 'cpu', root_body=self.meta['root_body'])
        self.task = Task(self.kin, torch.tensor(self.meta['q0']), torch.tensor(self.meta['soft_limits']),
                         torch.tensor(self.meta['action_scale']), self.cfg, 'cpu')
        self.task.set_joint_names(self.meta['joint_names'])
        self.policy = Policy(OBS_DIM * self.cfg.history, GOAL_FRAME_DIM * self.cfg.future,
                             latent=self.ck['cfg']['latent']).eval()
        self.policy.load_state_dict(self.ck['policy'])
        networks.AMP['enabled'] = False
        self.zero_bias = torch.zeros(1, 29)
        self.end = int(self.lib.lengths[0]) - 1
        self.clip = clip
        self.reset()

    def select_clip(self, clip):
        library = MotionLibrary(str(HERE / 'motions.npz'), 'cpu', keep={clip})
        if library.num_clips != 1:
            raise ValueError(f'Unknown motion {clip!r}; run with --list')
        self.lib = library
        self.end = int(library.lengths[0]) - 1
        self.clip = clip
        self.reset()

    def state(self):
        m, d = self.meta, self.data
        ra, va = m['root_qadr'], m['root_vadr']
        def tensor(x):
            return torch.tensor(np.array(x, copy=True), dtype=torch.float32).unsqueeze(0)
        rot = quat_to_mat(quat_normalize(tensor(d.qpos[ra+3:ra+7])))
        return {'pos': tensor(d.qpos[ra:ra+3]), 'rot': rot,
                'q': tensor(d.qpos[m['q_adr']]), 'qd': tensor(d.qvel[m['qd_adr']]),
                'v': tensor(d.qvel[va:va+3]),
                'w': (rot @ tensor(d.qvel[va+3:va+6]).unsqueeze(-1)).squeeze(-1)}

    def future(self):
        indices = torch.tensor([[min(self.frame + offset, self.end) for offset in self.cfg.offsets]])
        return self.lib.frame(indices)

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.frame = 0
        ref = self.lib.frame(torch.tensor([0]))
        m, d = self.meta, self.data
        ra, va = m['root_qadr'], m['root_vadr']
        d.qpos[ra:ra+3] = ref['pos'][0].numpy()
        d.qpos[ra+3:ra+7] = ref['quat'][0].numpy()
        d.qpos[m['q_adr']] = ref['q'][0].numpy()
        d.qvel[va:va+3] = ref['v'][0].numpy()
        d.qvel[va+3:va+6] = (ref['rot'][0].T @ ref['w'][0]).numpy()
        d.qvel[m['qd_adr']] = ref['qd'][0].numpy()
        mujoco.mj_forward(self.model, d)
        self.previous_action = torch.zeros(1, 29)
        self.current_state = self.state()
        obs = self.task.obs_clean(self.current_state, self.previous_action, self.zero_bias)
        self.history = obs.unsqueeze(1).repeat(1, self.cfg.history, 1)
        self.goal = self.task.goal(self.current_state, self.future())
        self.failed = False

    @torch.inference_mode()
    def step(self):
        action = self.policy(self.history.flatten(1), self.goal)
        reference = self.lib.frame(torch.tensor([self.frame + 1]))
        absolute_action = self.task.setpoint_action(action, reference['q'])
        target = self.task.q0 + self.task.action_scale * absolute_action
        self.data.ctrl[:] = target[0, self.meta['act_to_joint']].numpy()
        for _ in range(self.meta['decimation']):
            mujoco.mj_step(self.model, self.data)
        self.frame += 1
        self.current_state = self.state()
        finite = all(torch.isfinite(x).all().item() for x in self.current_state.values())
        self.failed = not finite or bool(self.task.termination(self.current_state, reference)[0].item())
        obs = self.task.obs_clean(self.current_state, action, self.zero_bias)
        self.history = torch.cat((self.history[:, 1:], obs.unsqueeze(1)), dim=1)
        self.goal = self.task.goal(self.current_state, self.future())
        self.previous_action = action
        return self.failed or self.frame >= self.end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List available reference motions')
    parser.add_argument('--clip', default='walk1_subject1.csv')
    parser.add_argument('--policy', type=Path, default=HERE / 'policy.pt')
    parser.add_argument('--headless', action='store_true', help='Run without an OpenGL window, as fast as possible')
    parser.add_argument('--no-gui', action='store_true', help='Open only the MuJoCo viewer, without the motion selector')
    parser.add_argument('--seconds', type=float, help='Limit simulated seconds; omitted means the whole motion')
    parser.add_argument('--loop', action='store_true', help='Restart after completion/failure, window mode only')
    parser.add_argument('--speed', type=float, default=1.0, help='Playback speed, e.g. 0.5 for half speed')
    parser.add_argument('--threads', type=int, default=2, help='CPU inference threads')
    parser.add_argument('--report', type=Path, help='Write headless result JSON')
    args = parser.parse_args()
    if args.speed <= 0 or args.threads <= 0 or (args.seconds is not None and args.seconds <= 0):
        parser.error('speed, threads and seconds must be positive')
    if args.list:
        with np.load(HERE / 'motions.npz', allow_pickle=False) as motions:
            for name, length in zip(motions['names'], motions['lengths']):
                print(f'{name:35s} {int(length)/float(motions["fps"]):7.2f} s')
        return 0
    if not args.headless and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        parser.error('No desktop display found. Run in the Ubuntu desktop terminal, or use --headless.')
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    player = Player(args.clip, args.policy)
    limit = min(player.end, int(args.seconds / player.cfg.dt)) if args.seconds else player.end
    print(f'Policy iteration {player.ck["iteration"]}; native MuJoCo CPU; {args.clip}; '
          f'control {1/player.cfg.dt:g} Hz, physics {1/player.model.opt.timestep:g} Hz', flush=True)
    started = time.perf_counter()
    if args.headless:
        while player.frame < limit and not player.step():
            pass
    else:
        import mujoco.viewer
        commands = queue.SimpleQueue()
        panel = None
        if not args.no_gui:
            from motion_gui import MotionSelector
            with np.load(HERE / 'motions.npz', allow_pickle=False) as archive:
                motions = [(str(name), (int(length) - 1) / float(archive['fps']))
                           for name, length in zip(archive['names'], archive['lengths'])]
            panel = MotionSelector(motions, args.clip, args.loop, args.speed,
                                   lambda action, value: commands.put((action, value)))
        def on_key(key):
            if key == 32:
                commands.put(('toggle_pause', None))
            elif key in (82, 114):
                commands.put(('restart', None))
        print('Space: pause/resume; R: restart; mouse: rotate/zoom; close window: exit', flush=True)
        try:
            with mujoco.viewer.launch_passive(player.model, player.data, key_callback=on_key) as viewer:
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
                viewer.cam.trackbodyid = player.meta['root_body']
                viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 3.0, 135.0, -15.0
                finished = paused = stopped = closing = False
                looping, speed = args.loop, args.speed
                if panel:
                    panel.show()
                while viewer.is_running() and not closing:
                    tick = time.perf_counter()
                    if panel and not panel.pump():
                        break
                    with viewer.lock():
                        while not commands.empty():
                            action, value = commands.get_nowait()
                            if action == 'close':
                                closing = True
                            elif action == 'play':
                                if panel:
                                    panel.show_loading(value)
                                try:
                                    if value != player.clip:
                                        player.select_clip(value)
                                    else:
                                        player.reset()
                                    limit = min(player.end, int(args.seconds / player.cfg.dt)) if args.seconds else player.end
                                    finished = paused = stopped = False
                                    print(f'[AllMimic] Playing {player.clip}', flush=True)
                                except (ValueError, OSError) as exc:
                                    paused = True
                                    if panel:
                                        panel.show_error(f'无法加载动作：{exc}')
                                    print(f'[AllMimic] Cannot load {value}: {exc}', file=sys.stderr, flush=True)
                            elif action == 'toggle_pause':
                                paused = not paused
                                stopped = False
                            elif action in ('restart', 'stop'):
                                player.reset()
                                finished = False
                                paused = stopped = action == 'stop'
                                if panel:
                                    panel.error_message = ''
                            elif action == 'loop':
                                looping = value
                            elif action == 'speed':
                                speed = value
                        if not closing and not paused and not finished:
                            finished = player.step() or player.frame >= limit
                            if finished:
                                print(f'End: clip={player.clip}, seconds={player.frame*player.cfg.dt:.2f}, '
                                      f'failed={player.failed}', flush=True)
                        if finished and looping and not paused and not closing:
                            player.reset()
                            finished = False
                    if closing:
                        break
                    viewer.sync()
                    if panel:
                        panel.update_state(player.clip, player.frame * player.cfg.dt,
                                           player.end * player.cfg.dt, paused, finished,
                                           player.failed, stopped)
                    time.sleep(max(0.0, player.cfg.dt / speed - (time.perf_counter() - tick)))
        finally:
            if panel:
                panel.close()
    result = {'clip': player.clip, 'policy_iteration': player.ck['iteration'],
              'backend': 'native MuJoCo CPU, FP32 policy',
              'steps': player.frame, 'total_steps': player.end,
              'simulated_seconds': player.frame * player.cfg.dt,
              'wall_seconds': time.perf_counter() - started,
              'failed': player.failed, 'completed_full_clip': player.frame == player.end and not player.failed}
    print(json.dumps(result, indent=2), flush=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    return 2 if player.failed else 0


if __name__ == '__main__':
    sys.exit(main())
