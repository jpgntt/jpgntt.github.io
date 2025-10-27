import tkinter as tk
from tkinter import ttk
import time
import threading
from queue import Queue, Empty

# ===== SOM (winsound no Windows; fallback caso indisponível) =====
try:
    import winsound
    def tone(freq, dur_ms):
        winsound.Beep(freq, dur_ms)  # bloqueante, mas rodará em thread separada
except Exception:
    print("[WARN] winsound indisponível, usando fallback (campainha do terminal)")
    def tone(freq, dur_ms):
        print(f"\a[BEEP {freq}Hz {dur_ms}ms]")
        time.sleep(dur_ms / 1000.0)

# === CONFIG ===
GAME_DURATION = 15 * 60  # 15:00 em segundos

# tons/durações
BEEP_SHORT = 500  # Hz
BEEP_LONG  = 700  # Hz
BEEP_DURATION_SHORT = 500  # ms
BEEP_DURATION_LONG  = 900  # ms

# Padrões:
# 'S' = curto, 'L' = longo. Combine como quiser, ex.: 'SS', 'LL', 'SLS'
MILESTONES = {
    600: 'SS',   # 10:00
    300: 'SS',   # 05:00
    120: 'SSS',  # 02:00
    60:  'SSS',  # 01:00
}

# Últimos 10 segundos (de 10 até 1). Use 'S', 'L' ou None para desativar.
LAST10_PATTERN = 'S'

# Fim da partida (t=0). Ex.: 'L', 'LL', 'SLL', etc.
END_PATTERN = 'L'


# ====== Worker de áudio não bloqueante ======
class BeepWorker:
    def __init__(self):
        self.q: Queue[str] = Queue()
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def enqueue(self, pattern: str):
        if pattern:
            self.q.put(pattern)

    def stop(self):
        self._stop.set()
        self.q.put(None)  # acorda a thread

    def _beep_once(self, symbol):
        symbol = symbol.upper()
        if symbol == 'S':
            tone(BEEP_SHORT, BEEP_DURATION_SHORT)
        elif symbol == 'L':
            tone(BEEP_LONG, BEEP_DURATION_LONG)

    def _run(self):
        while not self._stop.is_set():
            try:
                pattern = self.q.get(timeout=0.5)
            except Empty:
                continue
            if pattern is None:  # sinal de parada
                break
            # Toca o padrão completo sem bloquear o relógio principal
            print(f"[BEEP] padrão='{pattern}' (thread áudio)")
            for i, ch in enumerate(pattern, 1):
                print(f"  └─ toque {i}: {'curto' if ch.upper()=='S' else 'longo'}")
                self._beep_once(ch)
                time.sleep(0.1)  # espaçamento entre toques


class PlacarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🏑 Placar Bike Polo — Simulador (Responsivo, áudio assíncrono)")
        self.root.minsize(800, 500)

        # Estado
        self.time_left = GAME_DURATION
        self.running = False
        self.teamA = 0
        self.teamB = 0
        self.events_fired = set()

        # Áudio não bloqueante
        self.beep = BeepWorker()

        # ====== ESTILO (ttk) ======
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self.style.configure("TButton", padding=10, font=("Inter", 16, "bold"))
        self.style.configure("Time.TButton", padding=12, font=("Inter", 18, "bold"))
        self.style.configure("Big.TButton", padding=16, font=("Inter", 22, "bold"))
        self.style.configure("Play.TButton", padding=18, font=("Inter", 24, "bold"))

        # ====== LAYOUT PRINCIPAL ======
        self.top_frame = tk.Frame(self.root, bg="#111111")
        self.mid_frame = tk.Frame(self.root, bg="#181818")
        self.bottom_frame = tk.Frame(self.root, bg="#111111")

        self.top_frame.grid(row=0, column=0, sticky="nsew")
        self.mid_frame.grid(row=1, column=0, sticky="nsew")
        self.bottom_frame.grid(row=2, column=0, sticky="nsew")

        self.root.grid_rowconfigure(0, weight=2)
        self.root.grid_rowconfigure(1, weight=6)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # ====== TOPO: CRONÔMETRO ======
        self.time_label = tk.Label(
            self.top_frame,
            text=self.format_time(),
            fg="#FFFFFF",
            bg="#111111",
            font=("Inter", 64, "bold")
        )
        self.time_label.pack(expand=True, fill="both", padx=16, pady=8)

        # ====== MEIO: 3 COLUNAS ======
        self.mid_frame.grid_columnconfigure(0, weight=1, uniform="mid")
        self.mid_frame.grid_columnconfigure(1, weight=1, uniform="mid")
        self.mid_frame.grid_columnconfigure(2, weight=1, uniform="mid")
        self.mid_frame.grid_rowconfigure(0, weight=1)

        self.teamA_frame = tk.Frame(self.mid_frame, bg="#202020", highlightthickness=0)
        self.center_frame = tk.Frame(self.mid_frame, bg="#1c1c1c", highlightthickness=0)
        self.teamB_frame = tk.Frame(self.mid_frame, bg="#202020", highlightthickness=0)

        self.teamA_frame.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        self.center_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=16)
        self.teamB_frame.grid(row=0, column=2, sticky="nsew", padx=(8, 16), pady=16)

        self.build_team_panel(self.teamA_frame, "Equipe A", "#1E40AF", is_A=True)
        self.build_center_controls(self.center_frame)
        self.build_team_panel(self.teamB_frame, "Equipe B", "#B91C1C", is_A=False)

        # ====== RODAPÉ: ATALHOS ======
        self.shortcut_label = tk.Label(
            self.bottom_frame,
            text=("Atalhos: F5 start/pausa • F6 reset • F7 -30s • F8 +30s • "
                  "F9 → 00:20 • F10 → 01:00 • F11 → 02:00 • F12 → 05:00 • Ctrl+F12 → 10:00 • "
                  "Q/W A−/A+ • O/P B−/B+"),
            fg="#dddddd",
            bg="#111111",
            font=("Inter", 12, "normal"),
        )
        self.shortcut_label.pack(expand=True, fill="both", padx=16, pady=8)

        # ====== THREAD DO RELÓGIO (tempo real com monotonic) ======
        self.clock_thread = threading.Thread(target=self.clock_loop, daemon=True)
        self.clock_thread.start()

        # ====== BINDINGS ======
        self.bind_shortcuts()
        self.root.bind("<Configure>", self.on_resize)

    # ------------------ Construção de subpainéis ------------------
    def build_team_panel(self, parent, title, color_hex, is_A=True):
        title_label = tk.Label(parent, text=title, bg=parent["bg"], fg="#eaeaea", font=("Inter", 20, "bold"))
        title_label.pack(pady=(12, 6))

        score_label = tk.Label(parent, text="0", bg=parent["bg"], fg=color_hex, font=("Inter", 80, "bold"))
        score_label.pack(pady=(0, 12), padx=8)

        btns = tk.Frame(parent, bg=parent["bg"])
        btns.pack(pady=8)

        plus = ttk.Button(btns, text="+", style="Big.TButton",
                          command=(lambda: self.change_score('A', +1)) if is_A else (lambda: self.change_score('B', +1)))
        minus = ttk.Button(btns, text="−", style="Big.TButton",
                           command=(lambda: self.change_score('A', -1)) if is_A else (lambda: self.change_score('B', -1)))
        plus.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        minus.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        if is_A:
            self.label_A = score_label
        else:
            self.label_B = score_label

    def build_center_controls(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        for r in range(4):
            parent.grid_rowconfigure(r, weight=1)

        add_btn = ttk.Button(parent, text="+  Tempo (+30s)", style="Time.TButton",
                             command=lambda: self.change_time(+30))
        play_btn = ttk.Button(parent, text="▶ / ⏸", style="Play.TButton",
                              command=self.toggle_timer)
        sub_btn = ttk.Button(parent, text="−  Tempo (−30s)", style="Time.TButton",
                             command=lambda: self.change_time(-30))
        reset_btn = ttk.Button(parent, text="⟳  Reset (15:00)", style="Time.TButton",
                               command=self.reset_time)

        add_btn.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        play_btn.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        sub_btn.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        reset_btn.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

    # ------------------ Lógica/ajuda ------------------
    def bind_shortcuts(self):
        # Tempo
        self.root.bind("<F5>", lambda e: self.toggle_timer())
        self.root.bind("<F6>", lambda e: self.reset_time())
        self.root.bind("<F7>", lambda e: self.change_time(-30))
        self.root.bind("<F8>", lambda e: self.change_time(+30))
        self.root.bind("<F9>", lambda e: self.jump_to(20))
        self.root.bind("<F10>", lambda e: self.jump_to(60))
        self.root.bind("<F11>", lambda e: self.jump_to(120))
        self.root.bind("<F12>", lambda e: self.jump_to(300))
        self.root.bind("<Control-F12>", lambda e: self.jump_to(600))
        # Gols
        self.root.bind("<q>", lambda e: self.change_score('A', -1))
        self.root.bind("<w>", lambda e: self.change_score('A', +1))
        self.root.bind("<o>", lambda e: self.change_score('B', -1))
        self.root.bind("<p>", lambda e: self.change_score('B', +1))

    def on_resize(self, event):
        w = max(self.root.winfo_width(), 1)
        h = max(self.root.winfo_height(), 1)
        base = min(w, h)
        time_size  = max(36, int(base * 0.08))
        score_size = max(48, int(base * 0.10))
        title_size = max(16, int(base * 0.025))
        tips_size  = max(10, int(base * 0.015))
        self.time_label.configure(font=("Inter", time_size, "bold"))
        self.label_A.configure(font=("Inter", score_size, "bold"))
        self.label_B.configure(font=("Inter", score_size, "bold"))
        for frame in (self.teamA_frame, self.teamB_frame):
            for wdg in frame.winfo_children():
                if isinstance(wdg, tk.Label) and wdg.cget("text") in ("Equipe A", "Equipe B"):
                    wdg.configure(font=("Inter", title_size, "bold"))
        self.shortcut_label.configure(font=("Inter", tips_size, "normal"))

    # ------------------ Formatação ------------------
    def format_time(self, seconds=None):
        if seconds is None:
            seconds = self.time_left
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    # ------------------ Ações de UI ------------------
    def change_score(self, team, delta):
        if team == 'A':
            self.teamA = max(0, self.teamA + delta)
            self.label_A.config(text=str(self.teamA))
        else:
            self.teamB = max(0, self.teamB + delta)
            self.label_B.config(text=str(self.teamB))

    def change_time(self, delta):
        self.time_left = max(0, self.time_left + delta)
        self.time_label.config(text=self.format_time())
        print(f"[TIME ADJUST] Novo tempo: {self.format_time()} ({self.time_left}s)")
        self.purge_future_events()

    def jump_to(self, seconds_left):
        self.time_left = max(0, int(seconds_left))
        self.time_label.config(text=self.format_time())
        print(f"[JUMP] Pulou para {self.format_time()} ({self.time_left}s)")
        self.purge_future_events()

    def toggle_timer(self):
        self.running = not self.running
        print(f"[STATE] Timer {'INICIADO' if self.running else 'PAUSADO'} em {self.format_time()} ({self.time_left}s)")

    def reset_time(self):
        self.time_left = GAME_DURATION
        self.running = False
        self.time_label.config(text=self.format_time())
        self.events_fired.clear()
        print("[RESET] Tempo reiniciado para 15:00; eventos limpos.")

    def purge_future_events(self):
        before = len(self.events_fired)
        self.events_fired = {e for e in self.events_fired if not (isinstance(e, int) and e > self.time_left)}
        if self.time_left > 10:
            self.events_fired = {e for e in self.events_fired if not (isinstance(e, str) and e.startswith("last10_"))}
        after = len(self.events_fired)
        if before != after:
            print(f"[EVENTS] Limpamos marcadores futuros. Agora: {self.events_fired}")

    # ------------------ Relógio com monotonic + áudio assíncrono ------------------
    def clock_loop(self):
        """
        Loop de tempo real:
        - Usa time.monotonic() para agendar ticks a cada ~1.0s
        - Não bloqueia ao tocar sons (fila/worker de áudio)
        """
        next_tick = time.monotonic()
        while True:
            if self.running and self.time_left > 0:
                now = time.monotonic()
                if now >= next_tick:
                    # avança um segundo
                    self.time_left = max(0, self.time_left - 1)
                    self.time_label.after(0, lambda: self.time_label.config(text=self.format_time()))
                    print(f"[TICK] {self.format_time()} ({self.time_left}s)")

                    # 1) Marcos exatos
                    if self.time_left in MILESTONES and self.time_left not in self.events_fired:
                        pat = MILESTONES[self.time_left]
                        print(f"[EVENT] Marco {self.format_time()} → padrão '{pat}'")
                        self.beep.enqueue(pat)  # toca em thread separada
                        self.events_fired.add(self.time_left)

                    # 2) Últimos 10 segundos (10..1)
                    if 0 < self.time_left <= 10:
                        key = f"last10_{self.time_left}"
                        if key not in self.events_fired and LAST10_PATTERN:
                            print(f"[EVENT] Últimos 10s (t={self.time_left}) → padrão '{LAST10_PATTERN}'")
                            self.beep.enqueue(LAST10_PATTERN)
                            self.events_fired.add(key)

                    # 3) Fim
                    if self.time_left == 0 and 0 not in self.events_fired:
                        print(f"[EVENT] Fim da partida → padrão '{END_PATTERN}'")
                        self.beep.enqueue(END_PATTERN)
                        self.events_fired.add(0)
                        self.running = False

                    # agenda próximo tick com base no relógio monotônico
                    next_tick += 1.0

                # dorme só o necessário até o próximo tick (sem passar do ponto)
                time.sleep(max(0.0, next_tick - time.monotonic()))
            else:
                # se pausado, reancora o próximo tick para agora
                next_tick = time.monotonic() + 1.0
                time.sleep(0.1)

    def __del__(self):
        try:
            self.beep.stop()
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = PlacarApp(root)
    root.mainloop()
