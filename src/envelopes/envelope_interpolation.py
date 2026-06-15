# envelope_interpolation.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class InterpolationStrategy(ABC):
    """Strategy base per interpolazione."""
    
    @abstractmethod
    def evaluate(self, t: float, breakpoints: List[List[float]], **context) -> float:
        """Valuta l'envelope al tempo t."""
        pass
    
    @abstractmethod
    def integrate(self, from_t: float, to_t: float, 
                   breakpoints: List[List[float]], **context) -> float:
        """Integra il segmento tra from_t e to_t."""
        pass


class LinearInterpolation(InterpolationStrategy):
    """Interpolazione lineare tra breakpoints."""
    
    def evaluate(self, t: float, breakpoints: List[List[float]], **context) -> float:
        for i in range(len(breakpoints) - 1):
            t0, v0 = breakpoints[i]
            t1, v1 = breakpoints[i + 1]
            
            if t0 <= t <= t1:
                alpha = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return v0 + alpha * (v1 - v0)
        
        # Hold primo o ultimo valore
        if t < breakpoints[0][0]:
            return breakpoints[0][1]
        return breakpoints[-1][1]
    
    def integrate(self, from_t: float, to_t: float, 
                   breakpoints: List[List[float]], **context) -> float:
        """
        Integrazione lineare: area trapezio.
        """
        if from_t >= to_t:
            return 0.0
        
        total = 0.0
        
        for i in range(len(breakpoints) - 1):
            t0, v0 = breakpoints[i]
            t1, v1 = breakpoints[i + 1]
            
            # Skippa segmenti fuori range
            if to_t <= t0 or from_t >= t1:
                continue
            
            # Limita al segmento corrente
            seg_start = max(from_t, t0)
            seg_end = min(to_t, t1)
            
            if seg_start >= seg_end:
                continue
            
            # Valori ai bordi dell'intervallo
            if t1 > t0:
                v_start = v0 + (v1 - v0) * (seg_start - t0) / (t1 - t0)
                v_end = v0 + (v1 - v0) * (seg_end - t0) / (t1 - t0)
            else:
                v_start = v_end = v0
            
            # Area trapezio: (base * (h1 + h2)) / 2
            total += 0.5 * (v_start + v_end) * (seg_end - seg_start)
        
        
        # HOLD: Integra dopo l'ultimo breakpoint se necessario
        last_t = breakpoints[-1][0]
        last_v = breakpoints[-1][1]
        
        if to_t > last_t and from_t < to_t:
            hold_start = max(from_t, last_t)
            hold_end = to_t
            if hold_end > hold_start:
                total += last_v * (hold_end - hold_start)
        
        # HOLD: Integra prima del primo breakpoint se necessario
        first_t = breakpoints[0][0]
        first_v = breakpoints[0][1]
        
        if from_t < first_t:
            hold_start = from_t
            hold_end = min(to_t, first_t)
            if hold_end > hold_start:
                total += first_v * (hold_end - hold_start)
        
        return total



class StepInterpolation(InterpolationStrategy):
    """Interpolazione a gradini (hold values)."""
    
    def evaluate(self, t: float, breakpoints: List[List[float]], **context) -> float:
        # Trova ultimo breakpoint <= t
        for i in range(len(breakpoints) - 1, -1, -1):
            if t >= breakpoints[i][0]:
                return breakpoints[i][1]
        return breakpoints[0][1]
    
    def integrate(self, from_t: float, to_t: float, 
                   breakpoints: List[List[float]], **context) -> float:
        """
        Integrazione step: area rettangolo.
        """
        if from_t >= to_t:
            return 0.0
        
        total = 0.0
        
        for i in range(len(breakpoints) - 1):
            t0, v0 = breakpoints[i]
            t1, _ = breakpoints[i + 1]
            
            # Skippa segmenti fuori range
            if to_t <= t0 or from_t >= t1:
                continue
            
            # Limita al segmento corrente
            seg_start = max(from_t, t0)
            seg_end = min(to_t, t1)
            
            if seg_start >= seg_end:
                continue
            
            # Step: valore costante v0 (hold left)
            total += v0 * (seg_end - seg_start)
        
        
        # HOLD: Integra dopo l'ultimo breakpoint se necessario
        last_t = breakpoints[-1][0]
        last_v = breakpoints[-1][1]
        
        if to_t > last_t and from_t < to_t:
            hold_start = max(from_t, last_t)
            hold_end = to_t
            if hold_end > hold_start:
                total += last_v * (hold_end - hold_start)
        
        # HOLD: Integra prima del primo breakpoint se necessario
        first_t = breakpoints[0][0]
        first_v = breakpoints[0][1]
        
        if from_t < first_t:
            hold_start = from_t
            hold_end = min(to_t, first_t)
            if hold_end > hold_start:
                total += first_v * (hold_end - hold_start)
        
        return total

class CubicInterpolation(InterpolationStrategy):
    """
    Interpolazione cubic Hermite con Fritsch-Carlson.
    
    Usa integrazione numerica di Simpson per calcolare l'area.
    """
    
    def evaluate(self, t: float, breakpoints: List[List[float]], **context) -> float:
        tangents = context.get('tangents', [])
        
        for i in range(len(breakpoints) - 1):
            t0, v0 = breakpoints[i]
            t1, v1 = breakpoints[i + 1]
            
            if t0 <= t <= t1:
                m0 = tangents[i] if i < len(tangents) else 0
                m1 = tangents[i + 1] if i + 1 < len(tangents) else 0
                return self._cubic_hermite(t, t0, v0, m0, t1, v1, m1)
        
        # Hold primo o ultimo valore
        if t < breakpoints[0][0]:
            return breakpoints[0][1]
        return breakpoints[-1][1]
    
    def integrate(self, from_t: float, to_t: float, 
                   breakpoints: List[List[float]], **context) -> float:
        """
        Integrazione cubic usando regola di Simpson composita.
        
        Usa 10 sotto-intervalli per ogni segmento tra breakpoints consecutivi.
        Simpson: ∫f(x)dx ≈ (h/6) * [f(a) + 4*f(mid) + f(b)]
        """
        if from_t >= to_t:
            return 0.0
        
        tangents = context.get('tangents', [])
        total = 0.0
        
        for i in range(len(breakpoints) - 1):
            t0, v0 = breakpoints[i]
            t1, v1 = breakpoints[i + 1]
            
            # Skippa segmenti fuori range
            if to_t <= t0 or from_t >= t1:
                continue
            
            # Limita al segmento corrente
            seg_start = max(from_t, t0)
            seg_end = min(to_t, t1)
            
            if seg_start >= seg_end:
                continue
            
            # Ottieni tangenti per questo segmento
            m0 = tangents[i] if i < len(tangents) else 0.0
            m1 = tangents[i + 1] if i + 1 < len(tangents) else 0.0
            
            # Integra usando Simpson con 10 sotto-intervalli
            total += self._integrate_simpson(
                seg_start, seg_end,
                t0, v0, m0,
                t1, v1, m1
            )

        # HOLD: Integra dopo l'ultimo breakpoint se necessario
        last_t = breakpoints[-1][0]
        last_v = breakpoints[-1][1]
        
        if to_t > last_t and from_t < to_t:
            hold_start = max(from_t, last_t)
            hold_end = to_t
            if hold_end > hold_start:
                total += last_v * (hold_end - hold_start)
        
        # HOLD: Integra prima del primo breakpoint se necessario
        first_t = breakpoints[0][0]
        first_v = breakpoints[0][1]
        
        if from_t < first_t:
            hold_start = from_t
            hold_end = min(to_t, first_t)
            if hold_end > hold_start:
                total += first_v * (hold_end - hold_start)
        
        return total
    
    def _integrate_simpson(
        self,
        from_t: float, to_t: float,
        t0: float, v0: float, m0: float,
        t1: float, v1: float, m1: float
    ) -> float:
        """
        Integrazione Simpson composita su [from_t, to_t].
        
        Divide l'intervallo in n sotto-intervalli e applica Simpson su ciascuno.
        
        Args:
            from_t, to_t: limiti integrazione
            t0, v0, m0: breakpoint e tangente sinistra
            t1, v1, m1: breakpoint e tangente destra
        
        Returns:
            Area sotto la curva cubic
        """
        n = 10  # Numero di sotto-intervalli
        dt = (to_t - from_t) / n
        total = 0.0
        
        for i in range(n):
            # Estremi sotto-intervallo
            t_a = from_t + i * dt
            t_b = from_t + (i + 1) * dt
            t_mid = (t_a + t_b) / 2
            
            # Valuta cubic hermite ai tre punti
            v_a = self._cubic_hermite(t_a, t0, v0, m0, t1, v1, m1)
            v_mid = self._cubic_hermite(t_mid, t0, v0, m0, t1, v1, m1)
            v_b = self._cubic_hermite(t_b, t0, v0, m0, t1, v1, m1)
            
            # Simpson: (dt/6) * [f(a) + 4*f(mid) + f(b)]
            total += (dt / 6.0) * (v_a + 4.0 * v_mid + v_b)
        
        return total
    
    @staticmethod
    def _cubic_hermite(
        t: float,
        t0: float, v0: float, m0: float,
        t1: float, v1: float, m1: float
    ) -> float:
        """
        Interpolazione cubic Hermite tra due punti.
        
        Args:
            t: tempo di valutazione
            t0, v0, m0: tempo, valore, tangente del primo punto
            t1, v1, m1: tempo, valore, tangente del secondo punto
        
        Returns:
            Valore interpolato al tempo t
        """
        h = t1 - t0
        if h == 0:
            return v0
        
        # Normalizza t in [0, 1]
        s = (t - t0) / h
        s2 = s * s
        s3 = s2 * s
        
        # Basis functions di Hermite
        h00 = 2*s3 - 3*s2 + 1   # Punto iniziale
        h10 = s3 - 2*s2 + s      # Tangente iniziale
        h01 = -2*s3 + 3*s2       # Punto finale
        h11 = s3 - s2            # Tangente finale
        
        # Interpolazione Hermite
        return h00 * v0 + h10 * h * m0 + h01 * v1 + h11 * h * m1
