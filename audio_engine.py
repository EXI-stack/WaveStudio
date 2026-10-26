import os
import tempfile
import subprocess
import numpy as np
import imageio_ffmpeg


class AudioAnalyzer:
    def __init__(self, sample_rate=44100):
        self.sr = sample_rate
        self.audio_data = None
        self.duration = 0.0
        self.extracted_wav_path = None

        self.track_envelope = None
        self.vocal_envelope = None
        self.bass_envelope = None

        self.n_cal_bands = 64
        self.cal_freqs_centers = np.geomspace(30, 9500, self.n_cal_bands)
        self.band_peaks = np.ones(self.n_cal_bands, dtype=np.float32)
        self.band_median = np.zeros(self.n_cal_bands, dtype=np.float32)
        self.wave_peak = 0.5
        self.bass_ref_peak = 1.0

        self.prev_top = None
        self.prev_bottom = None
        self.prev_bass_punch = 0.0

    def cleanup_temp(self):
        if self.extracted_wav_path and os.path.exists(self.extracted_wav_path):
            try:
                os.remove(self.extracted_wav_path)
            except OSError:
                pass
        self.extracted_wav_path = None

    def load_audio(self, file_path: str):
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        cmd_pcm = [
            ffmpeg_exe, "-v", "error", "-i", file_path,
            "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", "1", "-ar", str(self.sr), "-"
        ]
        proc = subprocess.run(cmd_pcm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)

        if proc.returncode != 0 or len(proc.stdout) == 0:
            err_msg = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Не удалось извлечь аудиодорожку из файла.\n{err_msg}")

        self.cleanup_temp()
        fd, temp_wav = tempfile.mkstemp(prefix="wavestudio_audio_", suffix=".wav")
        os.close(fd)

        cmd_wav = [
            ffmpeg_exe, "-y", "-v", "error", "-i", file_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", str(self.sr), "-ac", "2", temp_wav
        ]
        proc_wav = subprocess.run(cmd_wav, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
        if proc_wav.returncode == 0 and os.path.exists(temp_wav):
            self.extracted_wav_path = temp_wav
        else:
            self.extracted_wav_path = file_path

        self.audio_data = np.frombuffer(proc.stdout, dtype=np.float32)
        self.duration = len(self.audio_data) / self.sr
        self.wave_peak = float(np.percentile(np.abs(self.audio_data), 98) + 1e-5)

        n_points = 1500
        if len(self.audio_data) >= n_points * 64:
            step = len(self.audio_data) // n_points
            chunks = self.audio_data[:step * n_points].reshape(n_points, step)

            rms = np.sqrt(np.mean(chunks ** 2, axis=1))
            self.track_envelope = np.clip(rms / (np.percentile(rms, 98) + 1e-6), 0.03, 1.0)

            fft_mags = np.abs(np.fft.rfft(chunks, axis=1))
            freqs = np.fft.rfftfreq(step, 1.0 / self.sr)

            bass_mask = (freqs >= 30) & (freqs < 250)
            vocal_mask = (freqs >= 250) & (freqs < 6500)

            b_env = np.mean(fft_mags[:, bass_mask], axis=1) if np.any(bass_mask) else rms
            v_env = np.mean(fft_mags[:, vocal_mask], axis=1) if np.any(vocal_mask) else rms

            b_p98 = float(np.percentile(b_env, 98) + 1e-6)
            v_p98 = float(np.percentile(v_env, 98) + 1e-6)
            self.bass_envelope = np.clip((b_env / b_p98) ** 1.45, 0.02, 1.0)
            self.vocal_envelope = np.clip((v_env / v_p98) ** 1.35, 0.02, 1.0)

            win_size = 2048
            n_fft_cal = 4096
            n_cal = min(450, len(self.audio_data) // win_size)
            cal_step = max(1, (len(self.audio_data) // win_size) // max(1, n_cal))
            idx_starts = np.arange(0, n_cal * cal_step, cal_step)[:n_cal] * win_size
            cal_chunks = np.array([self.audio_data[s:s + win_size] for s in idx_starts]) * np.hanning(win_size)
            cal_fft = np.abs(np.fft.rfft(cal_chunks, n=n_fft_cal, axis=1))
            cal_freqs = np.fft.rfftfreq(n_fft_cal, 1.0 / self.sr)

            edges = np.geomspace(28, 9600, self.n_cal_bands + 1)
            self.cal_freqs_centers = 0.5 * (edges[:-1] + edges[1:])

            for b in range(self.n_cal_bands):
                m = (cal_freqs >= edges[b]) & (cal_freqs < edges[b + 1])
                if np.any(m):
                    vals = np.max(cal_fft[:, m], axis=1)
                else:
                    idx = np.argmin(np.abs(cal_freqs - self.cal_freqs_centers[b]))
                    vals = cal_fft[:, idx]
                self.band_peaks[b] = max(float(np.percentile(vals, 97)), 1e-4)
                self.band_median[b] = float(np.percentile(vals, 25))

            kick_mask = (cal_freqs >= 35) & (cal_freqs <= 135)
            if np.any(kick_mask):
                self.bass_ref_peak = max(float(np.percentile(np.max(cal_fft[:, kick_mask], axis=1), 97)), 1e-4)
        else:
            self.track_envelope = np.ones(200, dtype=np.float32) * 0.2
            self.bass_envelope = np.ones(200, dtype=np.float32) * 0.2
            self.vocal_envelope = np.ones(200, dtype=np.float32) * 0.2
            self.band_peaks = np.ones(self.n_cal_bands, dtype=np.float32)
            self.band_median = np.zeros(self.n_cal_bands, dtype=np.float32)

        self.prev_top = None
        self.prev_bottom = None
        self.prev_bass_punch = 0.0

    def get_shape_envelope(self, num_bars: int, preset_idx: int, wave_type: str) -> np.ndarray:
        x = np.linspace(-1.0, 1.0, num_bars)
        if wave_type == "circle":
            a = np.linspace(0, 2 * np.pi, num_bars, endpoint=False)
            organic = (
                0.30 * np.sin(a * 3 + 0.4) +
                0.25 * np.cos(a * 5 - 0.8) +
                0.25 * np.sin(a * 9 + 1.2) +
                0.20 * np.cos(a * 15 - 0.3) +
                0.15 * np.sin(a * 21 + 0.7)
            )
            organic = (organic - organic.min()) / (organic.max() - organic.min() + 1e-6)
            return np.clip(0.05 + 0.92 * (organic ** 1.35), 0.04, 1.0)

        if preset_idx == 4:
            pattern = np.array([0.28, 0.62, 0.95, 0.52, 0.30, 0.72, 1.0, 0.50, 0.28])
            return np.interp(np.linspace(0, 1, num_bars), np.linspace(0, 1, len(pattern)), pattern)
        elif preset_idx == 1:
            lobes = 0.55 + 0.45 * np.cos(x * np.pi * 5.5) ** 2
            taper = np.clip(1.0 - (x ** 4) * 0.7, 0.2, 1.0)
            return lobes * taper
        elif preset_idx == 3:
            gaussian = np.exp(-2.8 * (x ** 2))
            modulation = 0.65 + 0.35 * np.sin(np.linspace(0, 8 * np.pi, num_bars)) ** 2
            return np.clip(gaussian * modulation, 0.03, 1.0)
        elif preset_idx == 2:
            idx = np.arange(num_bars)
            return 0.5 + 0.5 * np.abs(np.sin(idx * 1.7 + 0.5))
        else:
            return 0.8 + 0.2 * np.cos(x * np.pi)

    def _compute_calibrated_bands(self, freqs, fft_mag) -> np.ndarray:
        edges = np.geomspace(28, 9600, self.n_cal_bands + 1)
        norm_bands = np.zeros(self.n_cal_bands, dtype=np.float32)

        for b in range(self.n_cal_bands):
            m = (freqs >= edges[b]) & (freqs < edges[b + 1])
            if np.any(m):
                val = float(np.max(fft_mag[m]))
            else:
                val = float(np.interp(self.cal_freqs_centers[b], freqs, fft_mag))

            peak = self.band_peaks[b]
            floor = min(self.band_median[b] * 0.55, peak * 0.18)
            norm = (val - floor) / max(peak - floor, 1e-4)
            norm_bands[b] = norm

        norm_bands = np.clip(norm_bands, 0.0, 1.08)
        return np.clip(norm_bands ** 1.70, 0.0, 1.0)

    def _extract_circle_bars(self, freqs, fft_mag, center_sample: int,
                             bass_punch: float, num_bars: int, time_sec: float) -> np.ndarray:
        norm_bands = self._compute_calibrated_bands(freqs, fft_mag)
        bands32 = 0.5 * (norm_bands[0::2] + norm_bands[1::2])

        idx_order = np.array([
            0, 1,   14, 15,  6, 7,   22, 23,
            2, 3,   16, 17,  8, 9,   24, 25,
            4, 5,   18, 19,  10, 11, 26, 27,
            12, 13, 20, 21,  28, 29, 30, 31
        ])
        arranged = bands32[idx_order]

        shift = (time_sec * 1.8) % 32
        x_base = np.arange(32, dtype=np.float32)
        x_shifted = (x_base + shift) % 32
        arranged_rot = np.interp(
            x_shifted,
            np.append(x_base, 32),
            np.append(arranged, arranged[0])
        )

        half = num_bars // 2
        half_spec = np.interp(np.linspace(0, 1, half), np.linspace(0, 1, 32), arranged_rot)
        spec_circle = np.concatenate([half_spec, half_spec[::-1]])
        if len(spec_circle) < num_bars:
            spec_circle = np.pad(spec_circle, (0, num_bars - len(spec_circle)), mode="wrap")

        slice_len = 32
        total_slice = num_bars * slice_len
        w_start = max(0, min(len(self.audio_data) - total_slice, center_sample - total_slice // 2))
        if w_start >= 0 and w_start + total_slice <= len(self.audio_data):
            raw_slices = self.audio_data[w_start:w_start + total_slice].reshape(num_bars, slice_len)
            micro_wave = np.max(np.abs(raw_slices), axis=1) / self.wave_peak
            micro_wave = np.clip((micro_wave - 0.06) / 0.90, 0.0, 1.0) ** 1.5
            micro_wave = 0.5 * (micro_wave + micro_wave[::-1])
        else:
            micro_wave = np.zeros(num_bars, dtype=np.float32)

        angles = np.linspace(0, 2 * np.pi, num_bars, endpoint=False)
        bass_ripple = (0.5 + 0.5 * np.sin(angles * 5 - time_sec * 9.0)) * (bass_punch ** 1.4) * 0.30

        combined = spec_circle * 0.72 + micro_wave * 0.32 + bass_ripple

        kernel = np.array([0.18, 0.64, 0.18], dtype=np.float32)
        padded = np.concatenate([[combined[-1]], combined, [combined[0]]])
        smoothed = np.convolve(padded, kernel, mode="valid")

        return np.clip(smoothed, 0.02, 1.0)

    def _extract_band_bars(self, freqs, fft_mag, f_min, f_max, num_bars, symmetric=True):
        count = (num_bars + 1) // 2 if symmetric else num_bars
        target_freqs = np.geomspace(f_min, f_max, count)

        raw_vals = np.zeros(count, dtype=np.float32)
        edges = np.geomspace(f_min, f_max, count + 1)
        for i in range(count):
            mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
            if np.any(mask):
                raw_vals[i] = np.max(fft_mag[mask])
            else:
                raw_vals[i] = np.interp(target_freqs[i], freqs, fft_mag)

        ref_peaks = np.interp(target_freqs, self.cal_freqs_centers, self.band_peaks)
        ref_medians = np.interp(target_freqs, self.cal_freqs_centers, self.band_median)

        floors = np.minimum(ref_medians * 0.55, ref_peaks * 0.18)
        norm = (raw_vals - floors) / np.maximum(ref_peaks - floors, 1e-4)
        norm = np.clip(norm, 0.0, 1.08)

        exp_factor = 1.85 if f_max <= 300 else 1.60
        vals = np.clip(norm ** exp_factor, 0.0, 1.0)

        if count >= 5:
            kernel = np.array([0.16, 0.68, 0.16], dtype=np.float32)
            padded = np.pad(vals, (1, 1), mode="edge")
            vals = np.convolve(padded, kernel, mode="valid")

        if symmetric:
            if num_bars % 2 == 0:
                return np.concatenate([vals[::-1], vals])
            return np.concatenate([vals[::-1], vals[1:]])
        return vals

    def get_frame_data(self, time_sec: float, params: dict, reset_smoothing=False):
        num_bars = params["num_bars"]
        mode = params["mode"]
        wave_type = params["wave_type"]
        smoothing_pct = params["smoothing"] / 100.0
        preset_idx = params["preset_idx"]

        shape = self.get_shape_envelope(num_bars, preset_idx, wave_type)

        if self.audio_data is None or len(self.audio_data) == 0:
            params["_bass_punch"] = 0.0
            if wave_type == "circle":
                return shape, shape
            idx = np.linspace(0, 4 * np.pi, num_bars)
            demo_top = np.clip(shape * (0.45 + 0.35 * np.abs(np.sin(idx))), 0.04, 1.0)
            demo_bot = np.clip(demo_top * 0.9, 0.04, 1.0)
            return demo_top, demo_bot

        center_sample = int(time_sec * self.sr)
        win_size = 2048
        n_fft = 4096
        start = max(0, center_sample - win_size // 2)
        end = min(len(self.audio_data), start + win_size)

        chunk = np.zeros(win_size, dtype=np.float32)
        if end > start:
            chunk[:end - start] = self.audio_data[start:end]

        fft_mag = np.abs(np.fft.rfft(chunk * np.hanning(win_size), n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sr)

        kick_mask = (freqs >= 35) & (freqs <= 135)
        raw_kick = float(np.max(fft_mag[kick_mask])) if np.any(kick_mask) else 0.0
        bass_punch = float(np.clip((raw_kick / self.bass_ref_peak - 0.15) / 0.85, 0.0, 1.0) ** 1.6)

        if reset_smoothing:
            self.prev_bass_punch = bass_punch
        else:
            if bass_punch > self.prev_bass_punch:
                self.prev_bass_punch = self.prev_bass_punch * 0.12 + bass_punch * 0.88
            else:
                self.prev_bass_punch = self.prev_bass_punch * 0.72 + bass_punch * 0.28
        params["_bass_punch"] = float(self.prev_bass_punch)

        rms_now = np.sqrt(np.mean(chunk ** 2)) / max(self.wave_peak * 0.65, 1e-4)
        beat_boost = float(np.clip(rms_now, 0.0, 1.0) ** 1.4)

        if wave_type == "circle":
            live_circle = self._extract_circle_bars(
                freqs, fft_mag, center_sample, self.prev_bass_punch, num_bars, time_sec
            )
            if mode == 1:
                x_old = np.linspace(0, 1, len(self.track_envelope))
                x_new = np.linspace(0, 1, num_bars)
                env_track = np.interp(x_new, x_old, self.track_envelope)
                top_bars = np.clip(env_track * 0.45 + live_circle * 0.70, 0.02, 1.0)
            else:
                top_bars = live_circle
            bot_bars = top_bars

        elif mode == 0 or mode == 3:
            sym = (mode == 0)
            if wave_type == "split":
                top_bars = self._extract_band_bars(freqs, fft_mag, 250, 7500, num_bars, symmetric=sym)
                bot_bars = self._extract_band_bars(freqs, fft_mag, 32, 250, num_bars, symmetric=sym)
                top_bars = np.clip(top_bars * shape, 0.02, 1.0)
                bot_bars = np.clip(bot_bars * shape, 0.02, 1.0)
            else:
                top_bars = self._extract_band_bars(freqs, fft_mag, 38, 8500, num_bars, symmetric=sym)
                top_bars = np.clip((top_bars * 0.86 + beat_boost * 0.18) * shape, 0.02, 1.0)
                bot_bars = top_bars

        elif mode == 1:
            x_old = np.linspace(0, 1, len(self.track_envelope))
            x_new = np.linspace(0, 1, num_bars)
            pulse = 0.80 + 0.25 * beat_boost
            if wave_type == "split":
                top_bars = np.clip(np.interp(x_new, x_old, self.vocal_envelope) * pulse, 0.02, 1.0)
                bot_bars = np.clip(np.interp(x_new, x_old, self.bass_envelope) * pulse, 0.02, 1.0)
            else:
                top_bars = np.clip(np.interp(x_new, x_old, self.track_envelope) * shape * pulse, 0.02, 1.0)
                bot_bars = top_bars

        else:
            window_sec = 4.0
            sample_times = np.linspace(time_sec - window_sec / 2, time_sec + window_sec / 2, num_bars)
            env_idx = (sample_times / max(self.duration, 0.01)) * (len(self.track_envelope) - 1)
            valid = (env_idx >= 0) & (env_idx < len(self.track_envelope))
            top_bars = np.zeros(num_bars, dtype=np.float32)
            bot_bars = np.zeros(num_bars, dtype=np.float32)

            if wave_type == "split":
                top_bars[valid] = np.interp(env_idx[valid], np.arange(len(self.vocal_envelope)), self.vocal_envelope)
                bot_bars[valid] = np.interp(env_idx[valid], np.arange(len(self.bass_envelope)), self.bass_envelope)
            else:
                top_bars[valid] = np.interp(env_idx[valid], np.arange(len(self.track_envelope)), self.track_envelope)
                top_bars = np.clip(top_bars * shape, 0.02, 1.0)
                bot_bars = top_bars

        if reset_smoothing or self.prev_top is None or len(self.prev_top) != num_bars:
            self.prev_top = top_bars.copy()
            self.prev_bottom = bot_bars.copy()
        else:
            attack = 0.05 + 0.13 * smoothing_pct
            decay = 0.25 + 0.56 * smoothing_pct

            self.prev_top = np.where(
                top_bars > self.prev_top,
                self.prev_top * attack + top_bars * (1.0 - attack),
                self.prev_top * decay + top_bars * (1.0 - decay)
            )
            self.prev_bottom = np.where(
                bot_bars > self.prev_bottom,
                self.prev_bottom * attack + bot_bars * (1.0 - attack),
                self.prev_bottom * decay + bot_bars * (1.0 - decay)
            )

        return self.prev_top, self.prev_bottom