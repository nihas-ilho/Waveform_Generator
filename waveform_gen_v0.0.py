import tkinter as tk
from tkinter import ttk
from typing import List, Tuple


CELL_WIDTH = 20   # 1 ??? ???
CELL_HEIGHT = 60  # ?? ??
NUM_CYCLES = 2048   # ?? ?? ?
NUM_WAVES = 8       # ?? ??

HIGH_Y = 10               # High ?? Y ??
LOW_Y = CELL_HEIGHT - 10  # Low ?? Y ??
GRID_COLOR = "#cccccc"
WAVE_COLOR = "#000000"
SIDEBAR_WIDTH = 260  # fixed width for the pulse info pane


def find_high_pulses(waveform: List[int]) -> List[Tuple[int, int]]:
    """
    High ??? ?? (start_index, width) ???? ??.
    :param waveform: 0/1 ???, index = clock
    :return: [(start_index, width), ...]
    """
    pulses = []
    in_pulse = False
    start = 0

    for i, value in enumerate(waveform):
        if value == 1 and not in_pulse:
            in_pulse = True
            start = i
        elif value == 0 and in_pulse:
            in_pulse = False
            width = i - start
            pulses.append((start, width))

    # ??? 1? ??
    if in_pulse:
        width = len(waveform) - start
        pulses.append((start, width))

    return pulses


class WaveformEditor:
    """
    ?? ??(0/1)? ???? ?? ? ?? ??? GUI.
    """
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("Waveform Editor (Clock-based Pulse Width)")

        # 파형 리스트(각 0/1 시퀀스), 활성 파형 인덱스, 신호 이름
        self.waveforms: List[List[int]] = [[0] * NUM_CYCLES for _ in range(NUM_WAVES)]
        self.active_wave: int = 0
        self.signal_vars: List[tk.StringVar] = []
        self.canvases: List[tk.Canvas] = []
        self.grid_drawn: set[int] = set()  # 그리드는 한 번만 그림
        self._pending_update: Tuple[int, int, int] | None = None  # (wave_idx, index, value)
        self._after_id: str | None = None
        self.cursor_index: int = 0  # 키보드 입력용 현재 인덱스
        self._pulse_len_buf: str = ""  # 숫자 입력 버퍼(펄스 길이)

        self._create_widgets()
        self._draw_all()
        self.master.bind("<Key>", self._on_key)
        self.master.bind("<Return>", self._on_enter)
        self.master.bind("<Shift-Return>", self._on_enter_zero)

    def _create_widgets(self) -> None:
        """GUI widgets setup."""
        main_frame = ttk.Frame(self.master, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)

        # left: signal labels + canvases stacked vertically
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.grid(row=0, column=0, sticky="nw")
        canvas_frame.columnconfigure(0, weight=1)

        canvas_width = CELL_WIDTH * NUM_CYCLES
        canvas_height = CELL_HEIGHT

        rows_frame = ttk.Frame(canvas_frame)
        rows_frame.grid(row=0, column=0, sticky="nw")
        rows_frame.columnconfigure(1, weight=1)

        for idx in range(NUM_WAVES):
            row = ttk.Frame(rows_frame)
            row.grid(row=idx, column=0, sticky="w", pady=4)
            row.columnconfigure(1, weight=1)

            # ?? ?? ??
            sig_var = tk.StringVar(value=f"Signal {idx+1}")
            self.signal_vars.append(sig_var)
            label_frame = ttk.Frame(row, width=80, height=canvas_height)
            label_frame.grid(row=0, column=0, sticky="n", padx=(0, 6))
            label_frame.grid_propagate(False)

            signal_entry = ttk.Entry(
                label_frame,
                textvariable=sig_var,
                justify="center",
                width=12
            )
            signal_entry.place(relx=0.5, rely=0.5, anchor="center")

            # ?? ???
            canvas = tk.Canvas(
                row,
                width=canvas_width,
                height=canvas_height,
                bg="white"
            )
            canvas.grid(row=0, column=1, sticky="nw")
            self.canvases.append(canvas)

            # mouse bindings with wave index
            canvas.bind("<Button-1>", lambda e, w=idx: self._on_left_click(w, e))
            canvas.bind("<B1-Motion>", lambda e, w=idx: self._on_left_drag(w, e))
            canvas.bind("<Button-3>", lambda e, w=idx: self._on_right_click(w, e))
            canvas.bind("<B3-Motion>", lambda e, w=idx: self._on_right_drag(w, e))

        # status label
        self.status_var = tk.StringVar()
        self.status_var.set("??? ???? ????? ??? ???? (?=High, ?=Low)")

        status_label = ttk.Label(
            canvas_frame,
            textvariable=self.status_var,
            anchor="w"
        )
        status_label.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        # right: pulse info + buttons
        side_frame = ttk.Frame(main_frame, width=SIDEBAR_WIDTH)
        side_frame.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        side_frame.grid_propagate(False)

        ttk.Label(side_frame, text="High Pulse ?? (?? ??)", font=("", 10, "bold")).pack(anchor="w")

        self.text_info = tk.Text(side_frame, width=30, height=20)
        self.text_info.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(side_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        btn_clear = ttk.Button(btn_frame, text="Clear (??)", command=self._clear_waveform)
        btn_clear.pack(side=tk.LEFT, padx=2)

        btn_export = ttk.Button(btn_frame, text="Print Waveform", command=self._export_waveform)
        btn_export.pack(side=tk.LEFT, padx=2)

        btn_recalc = ttk.Button(btn_frame, text="Recalc Pulses", command=self._update_pulse_info)
        btn_recalc.pack(side=tk.LEFT, padx=2)

    # -------------------- ??? ?? -------------------- #

    def _draw_all(self) -> None:
        """?? ???? ?? ??."""
        for idx in range(NUM_WAVES):
            canvas = self.canvases[idx]
            canvas.delete("wave")
            self._draw_grid(canvas)
            self._draw_waveform(canvas, self.waveforms[idx])
        self._update_pulse_info()

    def _draw_one(self, wave_idx: int) -> None:
        """??? ??? ?? ?? (??? ? ?? ???)."""
        canvas = self.canvases[wave_idx]
        canvas.delete("wave")
        self._draw_grid(canvas)
        self._draw_waveform(canvas, self.waveforms[wave_idx])

    def _draw_grid(self, canvas: tk.Canvas) -> None:
        """?? ??? ???."""
        if id(canvas) in self.grid_drawn:
            return
        width = CELL_WIDTH * NUM_CYCLES
        height = CELL_HEIGHT

        mid_y = (HIGH_Y + LOW_Y) / 2
        canvas.create_line(0, mid_y, width, mid_y, fill=GRID_COLOR, dash=(2, 2), tags=("grid",))

        for i in range(NUM_CYCLES + 1):
            x = i * CELL_WIDTH
            canvas.create_line(x, 0, x, height, fill=GRID_COLOR, tags=("grid",))
            if i % 4 == 0:
                canvas.create_text(x + 2, height - 5, text=str(i), anchor="sw", fill="#666666", tags=("grid",))

        self.grid_drawn.add(id(canvas))

    def _draw_waveform(self, canvas: tk.Canvas, waveform: List[int]) -> None:
        """waveform ???? ???? ?? polyline ???."""
        points = []

        def y_level(value: int) -> int:
            return HIGH_Y if value == 1 else LOW_Y

        x0 = 0
        y0 = y_level(waveform[0])
        points.append((x0, y0))

        for i in range(1, NUM_CYCLES):
            prev_val = waveform[i - 1]
            cur_val = waveform[i]
            x = i * CELL_WIDTH
            if cur_val != prev_val:
                points.append((x, y_level(prev_val)))
                points.append((x, y_level(cur_val)))
            points.append((x, y_level(cur_val)))

        points.append((NUM_CYCLES * CELL_WIDTH, y_level(waveform[-1])))

        if len(points) >= 2:
            flat_points = []
            for (x, y) in points:
                flat_points.extend([x, y])
            canvas.create_line(*flat_points, fill=WAVE_COLOR, width=2, tags=("wave",))

    # -------------------- ??? ??? -------------------- #

    def _index_from_event(self, event: tk.Event) -> int:
        index = event.x // CELL_WIDTH
        if index < 0:
            index = 0
        if index >= NUM_CYCLES:
            index = NUM_CYCLES - 1
        return int(index)

    def _set_active_wave(self, wave_idx: int) -> None:
        self.active_wave = wave_idx

    def _apply_wave_value(self, wave_idx: int, index: int, value: int) -> None:
        """실제 파형 값 적용 + 즉시 그리기."""
        if 0 <= index < NUM_CYCLES:
            self.waveforms[wave_idx][index] = 1 if value else 0
            self.active_wave = wave_idx
            self._draw_one(wave_idx)
            self._update_pulse_info()
            self.status_var.set(f"클럭 {index}: {'HIGH(1)' if value else 'LOW(0)'} (파형 {wave_idx+1}) 로 설정")

    def _schedule_wave_value(self, wave_idx: int, index: int, value: int) -> None:
        """드래그 시 12ms로 스로틀링하여 적용."""
        self._pending_update = (wave_idx, index, value)
        if self._after_id is None:
            self._after_id = self.master.after(12, self._flush_pending_update)

    def _flush_pending_update(self) -> None:
        self._after_id = None
        if self._pending_update is None:
            return
        wave_idx, index, value = self._pending_update
        self._pending_update = None
        self._apply_wave_value(wave_idx, index, value)

    def _on_left_click(self, wave_idx: int, event: tk.Event) -> None:
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._apply_wave_value(wave_idx, index, 1)

    def _on_left_drag(self, wave_idx: int, event: tk.Event) -> None:
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._schedule_wave_value(wave_idx, index, 1)

    def _on_right_click(self, wave_idx: int, event: tk.Event) -> None:
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._apply_wave_value(wave_idx, index, 0)

    def _on_right_drag(self, wave_idx: int, event: tk.Event) -> None:
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._schedule_wave_value(wave_idx, index, 0)

    def _on_key(self, event: tk.Event) -> None:
        """숫자 입력으로 펄스 길이 버퍼 작성(Entry 포커스 시 무시)."""
        widget = self.master.focus_get()
        if isinstance(widget, tk.Entry):
            return
        ch = event.char or ""
        if ch.isdigit():
            self._pulse_len_buf += ch
            self.status_var.set(f"길이 입력: {self._pulse_len_buf} (시작 클럭 {self.cursor_index}, 파형 {self.active_wave+1})")

    def _apply_pulse_length(self, fill_value: int) -> None:
        """버퍼 길이를 사용해 클릭 위치부터 fill_value(0/1)로 채운다."""
        if not self._pulse_len_buf:
            return
        try:
            length = int(self._pulse_len_buf)
        except Exception:
            self._pulse_len_buf = ""
            return
        if length <= 0:
            self._pulse_len_buf = ""
            return
        start = self.cursor_index
        end = min(NUM_CYCLES, start + length)
        self.waveforms[self.active_wave][start:end] = [fill_value] * (end - start)
        self._pulse_len_buf = ""
        self._draw_one(self.active_wave)
        self._update_pulse_info()
        val_label = "HIGH" if fill_value == 1 else "LOW"
        self.status_var.set(f"클럭 {start}~{end-1} (총 {end-start}) {val_label} 설정 (파형 {self.active_wave+1})")

    def _on_enter(self, event: tk.Event) -> None:
        """Enter: 버퍼 길이만큼 HIGH 적용."""
        self._apply_pulse_length(1)

    def _on_enter_zero(self, event: tk.Event) -> None:
        """Shift+Enter: 버퍼 길이만큼 LOW 적용."""
        self._apply_pulse_length(0)

    # -------------------- Pulse 정보 / 유틸 -------------------- #

    def _update_pulse_info(self) -> None:
        """?? ?? ???? High ?? ?? ??."""
        waveform = self.waveforms[self.active_wave]
        pulses = find_high_pulses(waveform)

        self.text_info.delete("1.0", tk.END)

        self.text_info.insert(tk.END, f"?? ??: {self.active_wave + 1}\n")
        self.text_info.insert(tk.END, f"?? ?: {len(waveform)}\n")
        self.text_info.insert(tk.END, f"High ?? ??: {len(pulses)}\n\n")

        for idx, (start, width) in enumerate(pulses, start=1):
            self.text_info.insert(
                tk.END,
                f"Pulse {idx}: start = {start}, width = {width} clocks\n"
            )

        self.text_info.insert(tk.END, "waveform ???(0/1):\n")
        self.text_info.insert(tk.END, f"{waveform}\n")

    def _clear_waveform(self) -> None:
        """?? ??? Low(0)?? ???."""
        self.waveforms[self.active_wave] = [0] * NUM_CYCLES
        self._draw_one(self.active_wave)
        self._update_pulse_info()
        self.status_var.set(f"?? {self.active_wave + 1} cleared (all LOW).")

    def _export_waveform(self) -> None:
        """?? ??? ??? ??."""
        wf = self.waveforms[self.active_wave]
        print(f"Current waveform #{self.active_wave + 1} (0/1 list):")
        print(wf)

        pulses = find_high_pulses(wf)
        print("High pulses (start, width):")
        for p in pulses:
            print(p)


def main() -> None:
    root = tk.Tk()
    app = WaveformEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
