# envelope_segment.py
"""
Segment classes for Envelope system.

Design Pattern: Template Method
- Segment (ABC): defines interface
- NormalSegment: linear progression with hold at boundaries

Each Segment:
- Contains breakpoints in absolute time
- Delegates interpolation to InterpolationStrategy
- Knows how to evaluate() and integrate() itself
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from envelopes.envelope_interpolation import InterpolationStrategy


class Segment(ABC):
    """
    Abstract base class for envelope segments.
    
    A Segment represents a portion of an envelope with:
    - Breakpoints in absolute time
    - An interpolation strategy (linear/step/cubic)
    - Context data (e.g., tangents for cubic)
    
    Template Method Pattern:
    - Subclasses implement evaluate() and integrate()
    - Common functionality (bounds, validation) here
    """
    
    def __init__(
        self,
        breakpoints: List[List[float]],
        strategy: InterpolationStrategy,
        context: Dict[str, Any] = None
    ):
        """
        Initialize segment.
        
        Args:
            breakpoints: [[t, v], ...] in absolute time, sorted
            strategy: InterpolationStrategy instance
            context: Additional data (e.g., {'tangents': [...]})
        """
        if len(breakpoints) < 1:
            from shared.exceptions import InvalidFieldValueError
            raise InvalidFieldValueError(
                field="breakpoints",
                value=breakpoints,
                hint="Segment richiede almeno un breakpoint",
            )
        
        # Sort by time
        self.breakpoints = sorted(breakpoints, key=lambda p: p[0])
        self.strategy = strategy
        self.context = context or {}
        
        # Cache boundaries
        self.start_time = self.breakpoints[0][0]
        self.end_time = self.breakpoints[-1][0]
        self.duration = self.end_time - self.start_time
    
    @abstractmethod
    def evaluate(self, t: float) -> float:
        """
        Evaluate envelope at time t.
        
        Args:
            t: absolute time in seconds
            
        Returns:
            Envelope value at time t
        """
        pass
    
    @abstractmethod
    def integrate(self, from_t: float, to_t: float) -> float:
        """
        Integrate envelope between from_t and to_t.
        
        Args:
            from_t: start time (absolute)
            to_t: end time (absolute)
            
        Returns:
            Area under envelope curve
        """
        pass
    
    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"start={self.start_time:.3f}, "
            f"end={self.end_time:.3f}, "
            f"strategy={self.strategy.__class__.__name__})"
        )


class NormalSegment(Segment):
    """
    Standard envelope segment with hold behavior at boundaries.
    
    Behavior:
    - t < start_time: hold first value
    - start_time <= t <= end_time: interpolate
    - t > end_time: hold last value
    
    This is the standard envelope segment for all envelope phases.
    """
    
    def evaluate(self, t: float) -> float:
        """
        Evaluate with hold at boundaries.
        
        Examples:
            seg = NormalSegment([[0, 0], [1, 10]], linear_strategy)
            seg.evaluate(-0.5) → 0    # Hold before
            seg.evaluate(0.5) → 5     # Interpolate
            seg.evaluate(1.5) → 10    # Hold after
        """
        # Hold before segment
        if t < self.start_time:
            return self.breakpoints[0][1]
        
        # Hold after segment
        if t > self.end_time:
            return self.breakpoints[-1][1]
        
        # Delegate to strategy for interpolation
        return self.strategy.evaluate(t, self.breakpoints, **self.context)
    
    def integrate(self, from_t: float, to_t: float) -> float:
        """
        Integrate with hold regions.
        
        Breakdown:
        1. Hold before segment (if from_t < start_time)
        2. Interpolated region (overlap with [start_time, end_time])
        3. Hold after segment (if to_t > end_time)
        
        Examples:
            seg = NormalSegment([[0, 0], [1, 10]], linear_strategy)
            seg.integrate(-1, 0) → 0        # Hold first value (0)
            seg.integrate(0, 1) → 5         # Triangle area
            seg.integrate(1, 2) → 10        # Hold last value (10)
            seg.integrate(-1, 2) → 15       # All three regions
        """
        if from_t >= to_t:
            return 0.0
        
        total = 0.0
        
        # Region 1: Hold BEFORE segment
        if from_t < self.start_time:
            hold_end = min(to_t, self.start_time)
            hold_value = self.breakpoints[0][1]
            total += hold_value * (hold_end - from_t)
            from_t = hold_end
        
        if from_t >= to_t:
            return total
        
        # Region 2: INTERPOLATED region (overlap with segment)
        if from_t < self.end_time:
            interp_start = max(from_t, self.start_time)
            interp_end = min(to_t, self.end_time)
            
            if interp_end > interp_start:
                total += self.strategy.integrate(
                    interp_start, interp_end,
                    self.breakpoints,
                    **self.context
                )
                from_t = interp_end
        
        if from_t >= to_t:
            return total
        
        # Region 3: Hold AFTER segment
        if from_t >= self.end_time and to_t > from_t:
            hold_value = self.breakpoints[-1][1]
            total += hold_value * (to_t - from_t)
        
        return total
