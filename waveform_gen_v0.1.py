import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from typing import List, Tuple
import re


CELL_WIDTH = 20   # 1 ??? ???
CELL_HEIGHT = 60  # ?? ??
NUM_CYCLES = 32   # ?? ?? ?
NUM_WAVES = 3       # ?? ??

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
        self.mode_vars: List[tk.StringVar] = []  # 파형 타입: pwl(1회), pulse(주기 반복)
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
            row.columnconfigure(2, weight=0)

            # ?? ?? ??
            sig_var = tk.StringVar(value=f"Signal {idx+1}")
            self.signal_vars.append(sig_var)
            sig_var.trace_add("write", lambda *_args, widx=idx: self._on_signal_name_change(widx))
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

            # ★ 수정: 파형 타입을 "one-shot"과 "반복"으로 변경
            mode_var = tk.StringVar(value="one-shot")
            self.mode_vars.append(mode_var)
            mode_combo = ttk.Combobox(
                row,
                values=["one-shot", "반복"],
                textvariable=mode_var,
                width=8, # 텍스트 길이에 맞춰 너비 조정
                state="readonly"
            )
            mode_combo.grid(row=0, column=2, padx=(6, 0))

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

        btn_va = ttk.Button(side_frame, text="Export Verilog-A", command=self._export_veriloga)
        btn_va.pack(fill=tk.X, pady=(8, 0))

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
        self.master.focus_set()  # Entry 포커스 해제 → 숫자 입력 가능
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._apply_wave_value(wave_idx, index, 1)

    def _on_left_drag(self, wave_idx: int, event: tk.Event) -> None:
        self.master.focus_set()
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._schedule_wave_value(wave_idx, index, 1)

    def _on_right_click(self, wave_idx: int, event: tk.Event) -> None:
        self.master.focus_set()
        self._set_active_wave(wave_idx)
        index = self._index_from_event(event)
        self.cursor_index = index
        self._pulse_len_buf = ""
        self._apply_wave_value(wave_idx, index, 0)

    def _on_right_drag(self, wave_idx: int, event: tk.Event) -> None:
        self.master.focus_set()
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

    def _on_signal_name_change(self, wave_idx: int) -> None:
        """신호 이름이 'CLK'로 설정되면 자동으로 0/1 클럭 패턴 채움."""
        name = self.signal_vars[wave_idx].get().strip().lower()
        if name != "clk":
            return
        # ★ 수정: LOW(0)에서 시작하는 [0, 1, 0, 1...] 패턴으로 변경
        self.waveforms[wave_idx] = [i % 2 for i in range(NUM_CYCLES)]
        # ★ 추가: CLK 입력 시 모드를 자동으로 '반복'으로 설정
        try:
            self.mode_vars[wave_idx].set("반복")
        except Exception:
            pass
        self.active_wave = wave_idx
        self.cursor_index = 0
        self._pulse_len_buf = ""
        self._draw_one(wave_idx)
        self._update_pulse_info()
        self.status_var.set(f"파형 {wave_idx+1}: 이름이 'CLK'여서 자동 클럭 패턴을 채웠습니다.")

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

    def _parse_time_string(self, time_str: str) -> float:
        """단위가 있는 시간 문자열(예: "10ns", "1.5us")을 초 단위로 파싱합니다."""
        s = time_str.strip().lower()
        
        # 'u'를 그리스 문자 마이크로(μ) 대신 사용
        units = {
            'fs': 1e-15, 'ps': 1e-12, 'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1.0,
            'f': 1e-15,  'p': 1e-12,  'n': 1e-9,  'u': 1e-6,  'm': 1e-3,
        }

        # 'ms'의 's'를 먼저 잡지 않도록 긴 단위부터 확인
        unit_found = ''
        for unit in sorted(units.keys(), key=len, reverse=True):
            if s.endswith(unit):
                unit_found = unit
                break
                
        if unit_found:
            number_part = s[:-len(unit_found)]
            multiplier = units[unit_found]
        else: # 단위가 없으면 초(seconds)로 간주
            number_part = s
            multiplier = 1.0
            
        try:
            value = float(number_part)
            return value * multiplier
        except (ValueError, TypeError):
            raise ValueError(f"잘못된 시간 형식: '{time_str}'")


    def _export_veriloga(self) -> None:
        """현재 GUI 파형들을 Verilog-A PWL 소스 파일로 내보낸다."""
        # 파라미터 입력 받기
        try:
            # --- ★ 수정: 대화상자 문구 및 파서 적용 ---
            tclk_str = simpledialog.askstring(
                "Clock Period",
                "기본 클럭 1주기(tCK)의 시간을 입력하세요.\n(GUI 2칸에 해당)\n\n예: 10ns, 1.5us, 1e-9",
                parent=self.master
            )
            if not tclk_str:
                return
            tclk = self._parse_time_string(tclk_str)
            if tclk <= 0:
                raise ValueError("클럭 주기는 0보다 커야 합니다.")
        except ValueError as e:
            messagebox.showerror("입력 오류", f"클럭 주기 형식이 잘못되었습니다:\n{e}")
            return

        # --- ★ 수정: 시간 계산 로직 변경 ---
        # 사용자가 입력한 tclk는 기본 클럭 1주기(GUI 2칸)의 시간입니다.
        # 따라서 GUI 한 칸에 해당하는 시간(t_step)은 tclk / 2.0 입니다.
        t_step = tclk / 2.0

        try:
            vlow_str = simpledialog.askstring("VLOW", "Low 전압 값 (예: 0)", parent=self.master) or "0"
            vhigh_str = simpledialog.askstring("VHIGH", "High 전압 값 (예: 1.2)", parent=self.master) or "1.2"
            vlow = float(vlow_str)
            vhigh = float(vhigh_str)
        except Exception:
            messagebox.showerror("입력 오류", "전압 값을 올바르게 입력하세요.")
            return

        try:
            # --- ★ 수정: 대화상자 문구 및 파서 적용 ---
            edge_str = simpledialog.askstring("Edge time", "Rising/Falling time\n\n예: 10ps, 0.1ns", parent=self.master) or "10ps"
            edge_time = self._parse_time_string(edge_str)
            if edge_time < 0:
                raise ValueError("에지 시간은 음수가 될 수 없습니다.")
        except ValueError as e:
            messagebox.showerror("입력 오류", f"에지 시간 형식이 잘못되었습니다:\n{e}")
            return

        path = filedialog.asksaveasfilename(
            title="Verilog-A 파일 저장",
            defaultextension=".va",
            filetypes=[("Verilog-A", "*.va"), ("All Files", "*.*")]
        )
        if not path:
            return

        def to_pwl_points(wf: List[int]) -> List[Tuple[float, float]]:
            points: List[Tuple[float, float]] = []
            if not wf:
                return []
            cur_val = wf[0]
            cur_time = 0.0
            points.append((cur_time, vhigh if cur_val else vlow))
            for i in range(1, len(wf)):
                if wf[i] != cur_val:
                    cur_val = wf[i]
                    cur_time = i * t_step
                    points.append((cur_time, vhigh if cur_val else vlow))
            return points

        def sanitize(name: str, default: str = "wave") -> str:
            s = name.strip()
            if not s:
                s = default
            s = re.sub(r"[^A-Za-z0-9_]", "_", s)
            if not s:
                s = default
            if s and s[0].isdigit():
                s = f"w_{s}"
            return s

        # 출력 포트 이름 = 신호 이름(중복 시 접미사 부여)
        used = set()
        outs: List[str] = []
        for raw in self.signal_vars:
            base = sanitize(raw.get())
            candidate = base
            suffix = 1
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used.add(candidate)
            outs.append(candidate)

        port_list = ", ".join(outs)

        real_vars = []
        integer_vars = []
        initial_lines = []
        body_lines = []
        for idx, wf in enumerate(self.waveforms):
            mode = self.mode_vars[idx].get().strip().lower()
            pwl_pts = to_pwl_points(wf)

            if not pwl_pts:
                continue

            # 모든 파형은 중간 변수 vsel을 사용합니다.
            real_vars.append(f"vsel_{idx}")
            initial_val = pwl_pts[0][1]
            initial_lines.append(f"        vsel_{idx} = {initial_val:.12g};")

            is_pulse = (mode == "반복")
            if is_pulse:
                period = len(wf) * t_step
                if period <= 0:
                    is_pulse = False # 주기가 0 이하면 pwl로 처리

            if is_pulse:
                period = len(wf) * t_step
                
                # @cross() 이벤트를 위한 변수 선언
                integer_vars.append(f"n_{idx}")
                real_vars.append(f"tau_{idx}")
                
                # initial_step에서 상태 변수 초기화
                initial_lines.append(f"        n_{idx} = floor($abstime / {period:.12g});")
                
                body_lines.append(f"    // {outs[idx]} : 반복 (periodic, using @cross for stability)")
                # @cross 이벤트로 주기 경계마다 상태 변수 n_{idx} 업데이트
                body_lines.append(f"    @(cross($abstime - (n_{idx} + 1) * {period:.12g} + 1e-18, +1))")
                body_lines.append(f"        n_{idx} = n_{idx} + 1;")
                
                # 상태 변수를 이용해 주기 내 시간(tau) 계산
                body_lines.append(f"    tau_{idx} = $abstime - n_{idx} * {period:.12g};")

                # to_pwl_points를 거치지 않고 waveform 리스트에서 직접 Verilog-A 코드를 생성합니다.
                for i in range(len(wf)):
                    time_edge = (i + 1) * t_step
                    value = vhigh if wf[i] else vlow
                    if_clause = "if" if i == 0 else "else if"
                    body_lines.append(f"    {if_clause} (tau_{idx} < {time_edge:.12g}) vsel_{idx} = {value:.12g};")
                
                # 마지막 구간 (이론적으로는 도달하지 않지만 안전을 위해 추가)
                last_val = vhigh if wf[-1] else vlow
                body_lines.append(f"    else vsel_{idx} = {last_val:.12g};")

                body_lines.append("") # 가독성을 위한 빈 줄
            else: # ★ 수정: one-shot 모드 로직
                times = [pt[0] for pt in pwl_pts]
                vals = [pt[1] for pt in pwl_pts]
                end_time = NUM_CYCLES * t_step # GUI 윈도우 전체 시간

                body_lines.append(f"    // {outs[idx]} : one-shot (then holds LOW)")
                if len(times) <= 1:
                    # 파형이 변하지 않을 경우, 윈도우 시간 동안만 값을 유지하고 그 후 vlow로 변경
                    body_lines.append(f"    if ($abstime < {end_time:.12g}) vsel_{idx} = {vals[0]:.12g};")
                    body_lines.append(f"    else vsel_{idx} = {vlow:.12g};")
                else:
                    # 시간대별로 값 설정
                    for i in range(1, len(times)):
                        if_clause = "if" if i == 1 else "else if"
                        body_lines.append(f"    {if_clause} ($abstime < {times[i]:.12g}) vsel_{idx} = {vals[i-1]:.12g};")
                    # 마지막 PWL 포인트부터 GUI 윈도우 끝까지 마지막 값을 유지
                    body_lines.append(f"    else if ($abstime < {end_time:.12g}) vsel_{idx} = {vals[-1]:.12g};")
                    # GUI 윈도우가 끝나면 0 (vlow)으로 유지
                    body_lines.append(f"    else vsel_{idx} = {vlow:.12g};")
                body_lines.append("")

        # 모든 조건문 로직이 끝난 후, 마지막에 transition을 일괄 적용합니다.
        transition_lines = []
        for idx in range(len(self.waveforms)):
            if any(f"vsel_{idx}" in s for s in real_vars):
                transition_lines.append(f"    V({outs[idx]}) <+ transition(vsel_{idx}, 0, {edge_time:.12g});")

        declarations = []
        if real_vars:
            declarations.append("    real " + ", ".join(sorted(list(set(real_vars)))) + ";")
        if integer_vars:
            declarations.append("    integer " + ", ".join(sorted(list(set(integer_vars)))) + ";")
        declaration_block = "\n".join(declarations)

        initial_block = ""
        if initial_lines:
            initial_block_content = "\n".join(initial_lines)
            initial_block = f"""    @(initial_step) begin
{initial_block_content}
    end"""
        
        body_logic = "\n".join(body_lines)
        transition_logic = "\n".join(transition_lines)
        body = f"{initial_block}\n\n{body_logic}\n{transition_logic}" if initial_block else f"{body_logic}\n{transition_logic}"

        content = f"""// Auto-generated from WaveformEditor (all waves)
`include "discipline.h"
`include "constants.h"

module pwl_waves({port_list});
    output {port_list};
    electrical {port_list};

    parameter real vlow = {vlow};
    parameter real vhigh = {vhigh};

{declaration_block}

    analog begin
{body}
    end
endmodule
"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("완료", f"Verilog-A 파일 저장 완료:\n{path}")
        except Exception as e:
            messagebox.showerror("저장 실패", str(e))


def main() -> None:
    root = tk.Tk()
    app = WaveformEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
