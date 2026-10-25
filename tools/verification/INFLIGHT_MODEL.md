# Async video in-flight ownership model (experimental)

This is a **bounded state exploration**, not a proof of Rust or GPU safety. It is derived from the async-conversion branch's `InFlightGuard` in `src/session/stream/video/pipeline/mod.rs`, not from code on the current main branch.

## Model-to-code mapping

| Model transition | Async branch code path |
| --- | --- |
| `submit` | `InFlightGuard::new` increments `Arc<AtomicUsize>` |
| `send` | `ConsumerMessage::Frame(..., InFlightGuard)` accepted by `blocking_send` |
| `send rejected` | Failed `blocking_send` owns a rejected message; dropping it drops the guard |
| `producer cancelled` | Producer drops a guard before transferring it |
| `consume` | `ctx_rx.recv().await` yields the message and moves its guard into the loop |
| `consumer completed` | Loop iteration exits and the guard's `Drop` decrements |
| `consumer cancelled` | Consumer task drops its currently held guard |
| `queue dropped` | Closing/dropping receiver releases queued messages |
| `close sender/receiver` | Channel endpoint closure and teardown |

The model deliberately treats ownership as a single unique frame location and explores nondeterministic ordering of producer submission, channel acceptance/rejection, consumer processing, cancellation, and queue drops. Its invariant is that the in-flight count equals the number of live guards and each released frame accounts for exactly one release event. It explores three distinct frames by default, which is **not** an unbounded proof.

## Running

```sh
python3 tools/verification/inflight_model.py
python3 -m unittest discover -s tools/verification -p 'test_inflight_model.py' -v
```

The tests additionally mutate the model's rejected-send transition so it forgets to decrement the counter. The explorer must find a counterexample containing `send rejected`. This establishes sensitivity to one relevant defect class, not comprehensive coverage.

## Explicit exclusions

- `Ordering::Relaxed` memory visibility and the timing of the drop-to-catch-up gate
- Actual Tokio channel implementation, `blocking_send` semantics and task scheduler fairness
- Vulkan fences, DMA-BUF lifetime, GPU completion, or `EncodeFuture` internals
- `ResetCounters` ordering, packetization, client playback, and correctness of the encoded stream
- Encoder failures that destroy resources without following modeled guard ownership
- Rust destructor unwinding details, accidental `mem::forget`, and other code paths absent from the transition system

**Do not claim that the model proves the async PR correct.** Its usefulness depends on verifying the mapping against the actual branch, adding Rust integration tests for modeled failure paths, and updating it when the implementation changes.

This is intentionally a separate draft from telemetry and host smoke verification. Keep the model experimental until reviewed against the async PR and verified by CI.
