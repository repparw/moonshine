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

The model deliberately treats ownership as a single unique frame location and explores nondeterministic ordering of producer submission, channel acceptance/rejection, consumer processing, cancellation, and queue drops. It over-approximates some events: for example, the abstract queue-drop transition may occur before the receiver-close transition, whereas Tokio's actual queue destruction is tied to receiver lifetime. Thus a green exploration establishes only consistency of the abstract conservation rules; it does not establish faithful scheduler/channel semantics. Its invariant is that the in-flight count equals the number of live guards and each released frame accounts for exactly one release event. It explores three distinct frames by default, which is **not** an unbounded proof.

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

## Source review (2026-10-25)

On `experiment/async-color-conversion`, both normal encode and IDR re-encode create an `InFlightGuard` before `blocking_send(ConsumerMessage::Frame(...))`. The guard is moved into the message; on send failure the rejected message is dropped by the error handling, and the guard's `Drop` decrements the counter. In `run_packet_consumer`, each received message's guard stays bound as `_in_flight` through the frame-processing iteration, including early `continue` paths. Queue teardown drops any remaining guards. The producer reads the counter using `Ordering::Relaxed` for its backpressure gate, outside this model's scope.

The async branch now includes a direct Rust regression test `failed_blocking_delivery_returns_in_flight_slot` alongside existing `try_send` and queue-drop tests. Those tests are stronger evidence of actual Tokio/Rust ownership than this abstract model; neither exercises a real GPU or proves cancellation under all runtime schedules.
