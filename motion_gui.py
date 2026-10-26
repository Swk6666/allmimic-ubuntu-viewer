"""A small desktop control panel for the MuJoCo motion player."""

from pathlib import Path
import sys
import sysconfig

# Some standalone Python builds ship Tk without Xft. The local CPython 3.11
# bridge uses Ubuntu's Tk instead, so fontconfig and CJK fonts are available.
_native_dir = Path(__file__).resolve().parent / 'gui_runtime'
_native_module = _native_dir / ('_tkinter' + sysconfig.get_config_var('EXT_SUFFIX'))
if '_tkinter' not in sys.modules and _native_module.is_file():
    sys.path.insert(0, str(_native_dir))
    try:
        import _tkinter
    except ImportError:
        pass  # Use the bundled Tk if the system's Tk libraries are unavailable.
    finally:
        sys.path.remove(str(_native_dir))

import tkinter as tk
from tkinter import font, ttk


CATEGORIES = (
    ('fightAndSports', '运动 / 格斗'), ('fallAndGetUp', '跌倒起身'),
    ('dance', '舞蹈'), ('fight', '打斗'), ('jumps', '跳跃'),
    ('sprint', '冲刺'), ('walk', '步行'), ('run', '跑步'),
)


def category_for(name):
    return next((label for prefix, label in CATEGORIES if name.startswith(prefix)), '其他')


def clock(seconds):
    minutes, seconds = divmod(max(0.0, seconds), 60)
    return f'{int(minutes):02d}:{seconds:04.1f}'


class MotionSelector:
    def __init__(self, motions, initial_clip, loop, speed, on_command):
        self.motions = list(motions)
        self.on_command = on_command
        self.closed = False
        self.close_requested = False
        self.error_message = ''
        self.current_clip = initial_clip
        self.root = tk.Tk()
        self.root.withdraw()
        # The large virtual desktop reports an excessive point-to-pixel scale.
        # Keep this panel's font sizes consistent with its pixel-sized layout.
        self.root.tk.call('tk', 'scaling', 4 / 3)
        self.root.title('AllMimic · 动作选择')
        height = min(980, self.root.winfo_screenheight() - 120)
        self.root.geometry(f'720x{height}+40+60')
        self.root.minsize(650, 760)
        self.root.configure(background='#f4f7fb')
        self.root.protocol('WM_DELETE_WINDOW', self.request_close)
        self._style()

        self.search_var = tk.StringVar()
        self.category_var = tk.StringVar(value='全部类别')
        self.loop_var = tk.BooleanVar(value=loop)
        self.speed_var = tk.StringVar(value=f'{speed:g}×')
        self.count_var = tk.StringVar()
        self.current_var = tk.StringVar(value=initial_clip)
        self.state_var = tk.StringVar(value='正在播放')
        self.time_var = tk.StringVar(value='00:00.0')
        self.pause_var = tk.StringVar(value='暂停')

        body = ttk.Frame(self.root, style='Page.TFrame', padding=22)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)
        ttk.Label(body, text='AllMimic', style='Title.TLabel').grid(sticky='w')
        ttk.Label(body, text=f'动作播放器  ·  {len(self.motions)} 条参考动作',
                  style='Muted.TLabel').grid(row=1, sticky='w', pady=(2, 18))

        filters = ttk.Frame(body, style='Page.TFrame')
        filters.grid(row=2, sticky='ew', pady=(0, 12))
        filters.columnconfigure(0, weight=1)
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky='ew', ipady=5)
        ttk.Button(filters, text='清空', width=5,
                   command=lambda: self.search_var.set('')).grid(row=0, column=1, padx=6)
        categories = sorted({category_for(name) for name, _ in self.motions})
        self.category_combo = ttk.Combobox(
            filters, state='readonly', width=12, textvariable=self.category_var,
            values=('全部类别', *categories),
        )
        self.category_combo.grid(row=0, column=2, sticky='e')
        ttk.Label(filters, text='搜索动作名、类别或 subject 编号',
                  style='Muted.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(5, 0))

        listing = ttk.Frame(body, style='Card.TFrame')
        listing.grid(row=3, sticky='nsew')
        listing.rowconfigure(0, weight=1)
        listing.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=('name', 'category', 'duration'),
                                 show='headings', selectmode='browse', height=13)
        for column, label, width, stretch in (
            ('name', '动作文件', 335, True),
            ('category', '类别', 105, False),
            ('duration', '时长', 85, False),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=60,
                             anchor='w' if column != 'duration' else 'e', stretch=stretch)
        self.tree.tag_configure('playing', foreground='#1d4ed8')
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(listing, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind('<Double-1>', self._double_click)
        self.tree.bind('<Return>', lambda event: self.play_selected())

        note = ttk.Frame(body, style='Page.TFrame')
        note.grid(row=4, sticky='ew', pady=(6, 16))
        note.columnconfigure(0, weight=1)
        ttk.Label(note, text='双击动作，或选择后点击「播放所选」', style='Muted.TLabel').grid(sticky='w')
        ttk.Label(note, textvariable=self.count_var, style='Muted.TLabel').grid(row=0, column=1, sticky='e')

        current = ttk.Frame(body, style='Card.TFrame', padding=16)
        current.grid(row=5, sticky='ew')
        current.columnconfigure(0, weight=1)
        ttk.Label(current, textvariable=self.state_var, style='State.TLabel').grid(sticky='w')
        ttk.Label(current, textvariable=self.current_var, style='Current.TLabel').grid(
            row=1, sticky='w', pady=(5, 12))
        self.progress = ttk.Progressbar(current, mode='determinate', maximum=1)
        self.progress.grid(row=2, sticky='ew')
        ttk.Label(current, textvariable=self.time_var, style='CardMuted.TLabel').grid(
            row=3, sticky='e', pady=(5, 0))

        buttons = ttk.Frame(body, style='Page.TFrame')
        buttons.grid(row=6, sticky='ew', pady=(16, 12))
        for column in range(4):
            buttons.columnconfigure(column, weight=1, uniform='controls')
        self.play_button = ttk.Button(buttons, text='播放所选', style='Accent.TButton',
                                      command=self.play_selected)
        self.pause_button = ttk.Button(buttons, textvariable=self.pause_var,
                                       command=lambda: self.emit('toggle_pause'))
        self.restart_button = ttk.Button(buttons, text='从头重播',
                                         command=lambda: self.emit('restart'))
        self.stop_button = ttk.Button(buttons, text='停止', command=lambda: self.emit('stop'))
        for column, button in enumerate((self.play_button, self.pause_button,
                                         self.restart_button, self.stop_button)):
            button.grid(row=0, column=column, sticky='ew', padx=(0 if column == 0 else 7, 0), ipady=5)

        options = ttk.Frame(body, style='Page.TFrame')
        options.grid(row=7, sticky='ew')
        options.columnconfigure(1, weight=1)
        self.loop_check = ttk.Checkbutton(options, text='循环当前动作', variable=self.loop_var,
                                          command=lambda: self.emit('loop', self.loop_var.get()))
        self.loop_check.grid(row=0, column=0, sticky='w')
        ttk.Label(options, text='播放速度', style='Muted.TLabel').grid(row=0, column=2, padx=(0, 8))
        speeds = sorted({0.25, 0.5, 1.0, 1.5, 2.0, speed})
        self.speed_combo = ttk.Combobox(options, state='readonly', width=6,
                                        textvariable=self.speed_var,
                                        values=tuple(f'{value:g}×' for value in speeds))
        self.speed_combo.grid(row=0, column=3, sticky='e')
        self.speed_combo.bind('<<ComboboxSelected>>',
                              lambda event: self.emit('speed', float(self.speed_var.get().rstrip('×'))))
        ttk.Label(body, text='播放窗口：空格暂停 / 继续 · R 重播 · 鼠标调整视角',
                  style='Muted.TLabel').grid(row=8, sticky='w', pady=(16, 0))

        self.search_var.trace_add('write', lambda *_: self._filter())
        self.category_var.trace_add('write', lambda *_: self._filter())
        self._filter()
        if self.tree.exists(initial_clip):
            self.tree.selection_set(initial_clip)
            self.tree.focus(initial_clip)
            self.tree.see(initial_clip)

    def _style(self):
        available = set(font.families(self.root))
        family = next((name for name in ('Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans')
                       if name in available), 'Sans')
        # Xft can apply an additional desktop font scale, even to pixel fonts.
        # Normalize against actual metrics so rows and controls remain usable.
        probe = font.Font(root=self.root, family=family, size=-14)
        font_scale = min(1.0, 20 / max(1, probe.metrics('linespace')))
        def pixels(size):
            return -max(1, round(size * font_scale))
        font.nametofont('TkDefaultFont').configure(family=family, size=pixels(14))
        font.nametofont('TkTextFont').configure(family=family, size=pixels(14))
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('.', font=(family, pixels(14)), foreground='#172b43')
        style.configure('Page.TFrame', background='#f4f7fb')
        style.configure('Card.TFrame', background='#ffffff')
        style.configure('TLabel', background='#f4f7fb')
        style.configure('Title.TLabel', font=(family, pixels(28), 'bold'), foreground='#14263e')
        style.configure('Muted.TLabel', font=(family, pixels(12)), foreground='#65768c')
        style.configure('State.TLabel', background='#ffffff', foreground='#2563eb')
        style.configure('Current.TLabel', background='#ffffff', font=(family, pixels(17), 'bold'))
        style.configure('CardMuted.TLabel', background='#ffffff', foreground='#65768c', font=(family, pixels(12)))
        style.configure('TButton', padding=(9, 6))
        style.configure('Accent.TButton', foreground='#ffffff', background='#2563eb')
        style.map('Accent.TButton', background=[('active', '#1d4ed8'), ('pressed', '#1e40af')])
        style.configure('TCheckbutton', background='#f4f7fb')
        style.configure('Treeview', rowheight=31, background='#ffffff', fieldbackground='#ffffff',
                        borderwidth=0, font=(family, pixels(14)))
        style.configure('Treeview.Heading', background='#e9eef6', padding=(8, 9), font=(family, pixels(14), 'bold'))
        style.map('Treeview', background=[('selected', '#dbeafe')], foreground=[('selected', '#173e78')])
        style.configure('Horizontal.TProgressbar', background='#2563eb', troughcolor='#e9eef6')

    def _filter(self):
        selection = self.tree.selection()
        query = self.search_var.get().strip().casefold()
        category = self.category_var.get()
        self.tree.delete(*self.tree.get_children())
        for name, duration in self.motions:
            label = category_for(name)
            if query not in f'{name} {label}'.casefold():
                continue
            if category != '全部类别' and category != label:
                continue
            self.tree.insert('', 'end', iid=name, values=(name, label, f'{duration:.1f} 秒'),
                             tags=('playing',) if name == self.current_clip else ())
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])
        elif self.tree.exists(self.current_clip):
            self.tree.selection_set(self.current_clip)
        self.count_var.set(f'{len(self.tree.get_children())} / {len(self.motions)}')

    def _double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.play_selected()

    def emit(self, action, value=None):
        self.on_command(action, value)

    def play_selected(self):
        selection = self.tree.selection()
        if selection:
            self.emit('play', selection[0])

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def pump(self):
        if self.closed or self.close_requested:
            return False
        self.root.update_idletasks()
        self.root.update()
        return not self.close_requested

    def show_loading(self, clip):
        self.error_message = ''
        self.state_var.set(f'正在加载 {clip}…')
        self.root.update_idletasks()

    def show_error(self, message):
        self.error_message = message
        self.state_var.set(message)

    def update_state(self, clip, elapsed, duration, paused, finished, failed, stopped):
        if clip != self.current_clip:
            if self.tree.exists(self.current_clip):
                self.tree.item(self.current_clip, tags=())
            self.current_clip = clip
            if self.tree.exists(clip):
                self.tree.item(clip, tags=('playing',))
            self.current_var.set(clip)
        self.pause_var.set('继续' if paused else '暂停')
        self.progress.configure(maximum=max(duration, 0.001), value=elapsed)
        self.time_var.set(f'{clock(elapsed)} / {clock(duration)}')
        if self.error_message:
            state = self.error_message
        elif failed:
            state = '动作未通过 · 可重播或选择其他动作'
        elif stopped:
            state = '已停止'
        elif paused:
            state = '已暂停'
        elif finished:
            state = '播放完成'
        else:
            state = '正在播放'
        self.state_var.set(state)

    def request_close(self):
        self.close_requested = True
        self.emit('close')

    def close(self):
        if not self.closed:
            self.closed = True
            self.root.destroy()
