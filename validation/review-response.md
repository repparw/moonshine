# Review response and ownership audit

Reviewed fork HEAD: cee4e8b (includes the later blocking-send cancellation test).
Code changes address review 5643911233 and inline comment 4371377508. Full earlier
host and LG C3 evidence is preserved on this validation branch.

## Timing resolution

FrameStats.convert remains source-compatible and is documented as CPU conversion
preparation/submission, including input-slot and previous-converter waits. New
convert_submit() naming is used by benchmark consumers. New structured
convert_submit_us / convert_submit_p50,p95,p99_us keys coexist with legacy aliases;
conversion_timing="submission" identifies the semantics. Benchmark text labels
changed accordingly. No current-conversion CPU fence wait or GPU timestamp was
added. All repository consumers were checked: pipeline summaries/spikes,
FrameStats broadcast, benchmark accumulation, verbose output and matrix output.

## Idle IDR: confirmed, separate

Pinned pixelforge rotates its input slot after successful submission. The
Moonshine timeout branch selects the next slot, which can hold an older frame.
A direct GPU reproduction initialized both slots (black, white), requested an
idle IDR with no new upload, and decoded black again. Mean Y was
15.99875, 235.0, 15.99875 instead of approximately 16, 235, 235.
No async conversion call is involved. This predates the patch and does not
create a new async-specific dependency: prior encode ordering already waits for
the conversion on which that encode depends. The content selection is wrong in
both versions regardless of completion order.

The reproduction and fix-design cautions are on the separate
investigation/idle-frame-idr branch. No unrelated replay fix is included in PR #1.
The earlier real TV resume test forced an IDR with new captures arriving; it did
not cover this no-new-capture path.

## GPU ownership audit

Dependencies inspected: pixelforge 4f3ff5e963a733e4036fd0bcb62df33daeb4ca94,
ferriscope a5b1205d7f7c1177a73b3b0896a97b17917c90a5, and its locked Smithay
0ff00983b6007257a7a161a4fe8b14a778e2ac8f.

| Failure/transition | Ownership and disposition |
|---|---|
| Recording failure before submit | convert_async waits for its previous job first. The incoming frame/import enter failed_source, previous source remains retained, and the session exits. Converter teardown destroys any retained view before source/import drops. |
| Queue-submit host/device OOM | Vulkan requires submitted resource state to remain unaffected on these errors. No new conversion is accepted; pixelforge sets in_flight only after successful submission. Retention covers the new view until teardown. |
| Encoder submission failure after conversion submit | The converter still owns the frame/import. Session exit destroys/waits the converter before dropping those resources; has_encoded is not advanced. No uncertain slot is reused. |
| Timeline counter query failure | The frame is still present; the query uses ? before clearing it. Exiting the loop takes converter teardown, subject to its exceptional wait caveat below. |
| Successful conversion completion | The timeline signal covers ALL_COMMANDS. Only the Frame is released; the imported image Arc stays until old-view destruction on next conversion or teardown. |
| Cache eviction | The pending/failed source owns its own Arc<CachedImport>; importer eviction cannot destroy an image still held by a converter. |
| Consumer completion/cancellation | The consumer owns an EncodeFuture and InFlightGuard, not a compositor Frame. Dropping the future does not cancel accepted GPU work. The readback worker/encoder own encoder slots; converter-owned sources remain independently pinned. |
| Session/producer early return | Local converter map drops before the encoder/context parameters. Each converter field precedes retained sources, so normal fence completion/view destruction precede source/import destruction. |
| Compositor shutdown | DmaBufFrame owns plane FDs and a release guard; Vulkan import has its own allocation reference. A closed release channel is ignored by ferriscope. Smithay sync-point signaling uses a weak DRM device and can return InvalidInput after device teardown; the earlier uncontrolled shutdown log alone does not establish a DMA-BUF lifetime fault. |
| Device loss | The session terminates. Completion cannot be interpreted as a recoverable normal frame; no retry on the same encoder is attempted. Real device loss was not injected, and successful validation does not establish all driver recovery behavior. |

## Concrete dependency caveat: failed destruction wait

pixelforge ColorConverter::drop calls `let _ = self.wait_idle()` and then destroys
GPU resources. wait_idle returns immediately on an unsuccessful wait, before
clearing in_flight or destroying src_view. A failed wait is **not** necessarily
device loss: vkWaitForFences also permits out-of-host/device-memory errors.
Those errors do not establish completion of previously accepted work. If such
an error occurs while conversion remains pending, continuing destruction and
then releasing Moonshine's source can violate the intended completion contract.
This is a static, concrete error sequence, not an induced driver failure or
observed normal-path use-after-free. It is a pre-existing pixelforge cleanup
limitation (the synchronous conversion path also uses wait_idle), not a new
Moonshine submission/cancellation defect.

Relevant primary contracts:
[vkWaitForFences](https://docs.vulkan.org/refpages/latest/refpages/source/vkWaitForFences.html),
[vkQueueSubmit2](https://docs.vulkan.org/refpages/latest/refpages/source/vkQueueSubmit2.html).

The fix belongs in pixelforge's completion/teardown contract, with a way for a
caller retaining external sources to know that teardown reached completion or a
terminal lost-device state. Adding a second best-effort wait in Moonshine cannot
guarantee this when that wait can fail too. No indefinite retry, guessed success,
leaked compositor frames, extra buffers or fault injection on the production GPU
was introduced. This caveat needs dependency-owner review before claiming the
exceptional-path safety criterion is fully met.

## Recommendation

The reduced async patch can be reviewed independently of machine-specific
validation artifacts and Nix packaging. Normal-path ownership and cancellation
checks pass; the P2 timing issue is addressed. The idle-IDR issue is confirmed and
separate. Keep PR #1 draft: clarify/fix pixelforge's non-device-loss wait-error
contract before recommending upstream submission as ready. There remains no
demonstrated throughput or end-to-end-latency benefit; the intended benefit is
less CPU blocking and scheduling flexibility, weighed against ownership cost.

## Final clean-source verification

Clean candidate `22ba3fc` passed formatting, workspace/all-targets compilation,
workspace tests (138 passed, one ignored), and all-targets Clippy with warnings
denied. The complete package also built with the separate ash vendor correction
and explicit Nixpkgs revision `02c087f`; see `review-evidence/package-build.json`
and compressed final logs. Runtime source bytes match the candidate exactly.
PR head `ceddf41` has the same four-file upstream diff. No TV matrix was repeated
for these timing/documentation-only revisions.
