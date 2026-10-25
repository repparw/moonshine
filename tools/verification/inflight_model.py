"""Bounded ownership model for async Moonshine's InFlightGuard.

This is a deliberately *abstract* transition model, not a proof of Rust,
Tokio, pixelforge, Vulkan synchronization or atomic memory ordering.
"""

from collections import deque
from dataclasses import dataclass
from typing import NamedTuple


@dataclass(frozen=True)
class State:
    # (frame id, location): producer, queued, consumer, released
    owners: tuple[tuple[int, str], ...] = ()
    count: int = 0
    sender_open: bool = True
    receiver_open: bool = True
    next_frame: int = 0
    # Total number of release events, for a stronger exactly-once invariant.
    releases: int = 0


class Transition(NamedTuple):
    name: str
    state: State


def move(s: State, frame: int, destination: str, release: bool = False) -> State:
    owners = dict(s.owners)
    assert owners[frame] != "released"
    owners[frame] = destination
    return State(
        owners=tuple(sorted(owners.items())),
        count=s.count - int(release),
        sender_open=s.sender_open,
        receiver_open=s.receiver_open,
        next_frame=s.next_frame,
        releases=s.releases + int(release),
    )


def successors(s: State, max_frames: int = 3, broken_rejection: bool = False):
    """Enumerate possible ownership-changing operations, including races.

    A failed delivery owns its message until the error is dropped; that drop
    must release the guard. broken_rejection intentionally omits this release.
    """
    owners = dict(s.owners)
    if s.sender_open and s.next_frame < max_frames:
        frame = s.next_frame
        yield Transition(
            f"submit {frame}",
            State(
                owners=tuple(sorted((*s.owners, (frame, "producer")))),
                count=s.count + 1,
                sender_open=s.sender_open,
                receiver_open=s.receiver_open,
                next_frame=frame + 1,
                releases=s.releases,
            ),
        )
    if s.sender_open:
        yield Transition(
            "close sender",
            State(s.owners, s.count, False, s.receiver_open, s.next_frame, s.releases),
        )
    if s.receiver_open:
        yield Transition(
            "close receiver",
            State(s.owners, s.count, s.sender_open, False, s.next_frame, s.releases),
        )
    for frame, owner in owners.items():
        if owner == "producer":
            if s.receiver_open:
                yield Transition(f"send {frame}", move(s, frame, "queued"))
            else:
                yield Transition(
                    f"send rejected {frame}",
                    move(s, frame, "released", release=not broken_rejection),
                )
            yield Transition(f"producer cancelled {frame}", move(s, frame, "released", release=True))
        elif owner == "queued":
            if s.receiver_open:
                yield Transition(f"consume {frame}", move(s, frame, "consumer"))
            yield Transition(f"queue dropped {frame}", move(s, frame, "released", release=True))
        elif owner == "consumer":
            yield Transition(f"consumer completed {frame}", move(s, frame, "released", release=True))
            yield Transition(f"consumer cancelled {frame}", move(s, frame, "released", release=True))


def invariant(s: State) -> str | None:
    owners = dict(s.owners)
    live = sum(owner != "released" for owner in owners.values())
    released = sum(owner == "released" for owner in owners.values())
    if s.count != live:
        return f"in-flight count {s.count} != live guards {live}"
    if s.count < 0:
        return "in-flight count underflow"
    if s.releases != released:
        return f"release events {s.releases} != released frames {released}"
    if s.next_frame != len(owners):
        return "frame IDs are not unique or a frame disappeared"
    return None


def explore(max_frames: int = 3, broken_rejection: bool = False):
    """Breadth-first search; returns visited states and shortest bad trace."""
    if max_frames < 1:
        raise ValueError("max_frames must be positive")
    initial = State()
    queue = deque([(initial, ())])
    visited = {initial}
    while queue:
        state, trace = queue.popleft()
        failure = invariant(state)
        if failure is not None:
            return visited, (trace, failure, state)
        for name, next_state in successors(state, max_frames, broken_rejection):
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, (*trace, name)))
    return visited, None


if __name__ == "__main__":
    states, counterexample = explore()
    print(f"Checked {len(states)} distinct states with 3 frame identities")
    if counterexample:
        trace, failure, state = counterexample
        print("Invariant violation:", failure)
        print("Trace:", " -> ".join(trace))
        print("State:", state)
        raise SystemExit(1)
    print("No invariant violations within the abstract bound")
