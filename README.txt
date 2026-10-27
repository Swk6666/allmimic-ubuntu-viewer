AllMimic — Ubuntu CPU MuJoCo 播放包（55 条动作）

1. 解压后在 Ubuntu 桌面环境的终端运行：

   cd allmimic-ubuntu-viewer
   bash setup.sh
   bash run.sh --loop

默认同时打开 MuJoCo 播放窗口和「AllMimic · 动作选择」面板。面板包含
全部 55 条动作，可搜索动作名、按类别筛选，并显示各动作时长。
双击动作，或选中后点击「播放所选」，即可在同一个 MuJoCo 窗口切换。
面板支持暂停/继续、从头重播、停止、循环开关和播放速度调整，并显示
当前正在播放的动作和进度。关闭任意一个窗口都会退出整个播放器。

首次安装需要联网。setup.sh 将 uv、Python 3.11、PyTorch 和 MuJoCo
安装在本目录的 runtime/、.venv/ 中，缓存默认也在本目录；无需 Conda、
单独安装 CUDA 工具包、mjlab 或管理员权限，也不会修改 shell 配置。Ubuntu 22.04/24.04 x86_64
可按此流程安装；其他架构和系统版本未在本次验证中测试。
本机安装按用户要求改用 GPU 版 PyTorch 2.14.1（CUDA 13.0）；优先使用
dependencies/ 中从原 AutoDL 环境校验迁移的依赖包。CPU 版可指定
TORCH_BACKEND=cpu bash setup.sh。可用 UV_CACHE_DIR 指定已有 uv 缓存。
播放器的物理仿真和策略推理仍保留原包的 CPU FP32 路径。
MuJoCo 窗口需要桌面显示和可用的 OpenGL 驱动。普通 SSH 终端不能直接
打开本地桌面窗口，请在目标 Ubuntu 电脑的桌面终端运行。

2. 查看和切换动作：

   bash run.sh --list
   bash run.sh --clip dance1_subject1.csv --loop
   bash run.sh --clip fallAndGetUp2_subject2.csv --loop
   bash run.sh --clip jumps1_subject2.csv --loop
   bash run.sh --clip walk1_subject1.csv --speed 0.5 --loop
   bash run.sh --clip flip_360_001__A304.csv --loop
   bash run.sh --clip cartwheel_R_001__A304.csv --loop

本次新增九条动作（文件名原样传给 --clip）：
  cartwheel_R_001__A304.csv                     侧手翻（4.68 秒）
  tiger_jump_to_shoulder_roll_R_001__A415.csv   虎跃接肩部滚翻起身（5.56 秒）
  turn_jump_360_R_001__A418.csv                 向右转身跳，约 180 度（4.90 秒）
  lateral_hop_R_001__A359.csv                   连续左右侧向跳（5.24 秒）
  shadow_boxing_R_001__A359.csv                 快速空击拳（8.80 秒）
  dance_hiphop_happy_feet_R_fast_001__A316.csv   快速街舞 Happy Feet（3.66 秒）
  handstand_idle_start_002__A304.csv            站立进入倒立（7.28 秒）
  handstand_ff_loop_180_R_001__A304.csv         倒立行走（5.80 秒）
  handstand_jump_004__A304.csv                  倒立跳跃（4.48 秒）
GUI 新增倒立、侧手翻、虎跃滚翻、转身跳、侧向跳、拳击分类，街舞归入舞蹈。
倒立行走、倒立跳跃可从参考倒立姿态初始化；站立进入倒立有单独的参考片段。

此前新增六条动作：
  broad_jump_002__A359.csv              向前远跳（5.24 秒）
  side_roll_R_002__A304.csv             向右侧滚（4.90 秒）
  flip_090_001__A304.csv                助跑向左侧空翻（7.18 秒）
  flip_180_R_001__A304.csv              助跑前空翻（5.58 秒）
  flip_360_001__A304.csv                后空翻（7.14 秒）
  flip_360_hero_landing_001__A304.csv   后空翻接单膝落地（8.54 秒）
动作面板保留「远跳」「侧滚」「空翻」分类。

空格：暂停/继续；R：从头重播；鼠标：旋转、移动、缩放视角；关闭窗口退出。
不加 --loop 时，动作结束或触发失败判定后停在最后状态，仍可按 R 重播。

只打开原来的 MuJoCo 窗口（不显示动作面板）：

   bash run.sh --no-gui --clip walk1_subject1.csv --loop

选择面板使用 Tkinter；gui_runtime/ 中保存本机中文字体支持模块及说明。
无窗口检查和 --list 不启动 GUI。

3. 无窗口检查（适用于服务器或排查安装问题）：

   bash run.sh --headless --seconds 10
   bash run.sh --headless --clip walk1_subject1.csv

--seconds 限制的是仿真时间，省略时测试整条动作。输出 failed 表示是否
触发原项目的失败条件；completed_full_clip 只有整条动作完成时才为 true。
失败返回码为 2。播放速度不足时，可试 --threads 1 或 --speed 0.5。

4. 模型与参考动作

policy.pt 是第 36,000 次迭代的策略网络、归一化统计和配置（约 37 MB）。
motions.npz 包含原 40 条 LAFAN1、此前六条和本次九条 BONES G1 参考动作
（50 Hz）；升级前全部 46 条参考数据与旧版本逐项一致。机器人描述、
碰撞体、驱动器及网格在 robot/ 中；robot_metadata.json 保存动作缩放、
默认关节角、关节映射和仿真设置。

该策略需要目标参考动作，不是仅给速度指令就能自主行走的控制器。脚本
每 20 ms 将最近 10 帧观测和未来 10 帧参考送入策略，生成关节目标，
由 MuJoCo 以 5 ms 步长进行真实物理仿真；不是直接播放参考关节动画。

原训练和评估使用 GPU MuJoCo Warp；此包使用原生 CPU MuJoCo 和 FP32
策略推理。两种物理后端存在数值差异，所以原 GPU 的成功率不能直接当作
此 CPU 播放器的成功率。新播放包在导出机器上验证了本次九条、此前六条和
完整步行，结果见 validation/export-55/。当前 Ubuntu 电脑已完整验证本次九条、
此前六条及原步行、舞蹈、跌倒起身、跳跃四条，共 19 条全部通过；55 条列表、
分类、九条新动作切换及播放控制的 GUI 测试也通过。汇总见
validation/ubuntu-55-summary.json，完整本机日志位于 validation/local-machine/mixed55/。
上次第 30,000 次策略的导出和本机报告仍保存在 validation/export-46/ 和
validation/local-machine/mixed46/。
旧版第 18,000 次策略的原始验证结果保留在 validation/previous-40/；
以前的本机环境、CUDA 和 GUI 验证结果仍保存在 validation/local-machine/。

来源：Shimingyi/allmimic，commit cb334ff674b2f57248f33f8c21b7fb526fbdf8cc。
训练检查点：runs/mixed55_phase1/ckpt_0036000.pt（best.pt）。
该检查点 GPU 独立评估和复测的完整动作均为原动作 40/40、此前六条 6/6、
本次九条 9/9；10 秒短片段评估及复测均为 895/896。详见 training_validation.json。
新增数据源为 BONES 的 seed-viewer.bones.studio 逐动作 G1 CSV 接口；
动作帧数及数据校验记录见 motion_sources.json。

5. 迁移与删除

只需复制整个压缩包，在目标电脑解压并重新运行 setup.sh。
不要复制原机器的 .venv；环境通常包含机器上的绝对路径。
关闭播放进程后，删除整个 allmimic-ubuntu-viewer 目录即可删除本包创建的文件。
安装后若移动了目录，删除本包的 .venv 子目录并重新运行 setup.sh。

依赖说明：
  MuJoCo Python viewer: https://mujoco.readthedocs.io/en/stable/python.html
  uv 本地安装选项: https://docs.astral.sh/uv/reference/installer/
源代码及机器人资产的原有声明保存在 LICENSE-upstream.txt、LICENSE-mjlab.txt。
模型与参考动作通过 Git LFS 保存；数据来源与许可说明见 README.md。
