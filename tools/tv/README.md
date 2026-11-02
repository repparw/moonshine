# LG/webOS Moonlight verification (fork-specific)

**Status:** launch path source-reviewed and CLI command construction unit-tested; **not** validated on the physical LG C3. These helpers are specific to our fork and are not intended for the generic upstream Moonshine verification PR.

## Why launch parameters may work

Moonlight's webOS client reads `host_uuid` and `host_app_id` from the JSON payload passed when its native application launches. Its launcher locates that previously paired host and automatically starts the requested app if it appears in the host's app list.

Source:
- [webOS parameter parsing](https://github.com/mariotaku/moonlight-tv/blob/main/src/app/platform/webos/app_webos.c)
- [host selection](https://github.com/mariotaku/moonlight-tv/blob/main/src/app/ui/launcher/launcher.controller.c)
- [app auto-launch](https://github.com/mariotaku/moonlight-tv/blob/main/src/app/ui/launcher/apps.controller.c)
- [LG webOS CLI `ares-launch --params`](https://webostv.developer.lge.com/develop/tools/webos-tv-cli-dev-guide)

This relies on the *installed* Moonlight client supporting those fields. Confirm its revision before depending on this for unattended tests.

## Prerequisites

Configure webOS TV CLI and a device alias following LG's official documentation. Confirm `ares-launch --device <alias> --running` and `ares-install --device <alias> --list` work. Determine Moonlight's actual **installed app ID** from that device, the **paired host UUID** from its configuration, and an **app ID advertised by Moonshine**; these are not IP addresses or automatically inferred.

Commands use `python3 tools/tv/verify_tv.py` from the repository root.

## Safe procedures

Only construct a launch command (does **not** contact the TV):

```sh
python3 tools/tv/verify_tv.py plan --device living-room --app-id YOUR_MOONLIGHT_APP_ID \
  --host-uuid YOUR_PAIRED_HOST_UUID --host-app-id 1
```

Query running applications (read-only):

```sh
python3 tools/tv/verify_tv.py doctor --device living-room --app-id YOUR_MOONLIGHT_APP_ID
```

To request a real launch, only when the TV is available for testing:

```sh
python3 tools/tv/verify_tv.py start --device living-room --app-id YOUR_MOONLIGHT_APP_ID \
  --host-uuid YOUR_PAIRED_HOST_UUID --host-app-id 1 --confirm --out target/tv-verification/run-001
```

The helper refuses to launch when Moonlight is already listed as running, and records the request and launcher response. It does **not** stop the TV app, change persistent client settings, restart Moonshine, change inputs, or assert that streaming succeeded. Use a new empty evidence directory each run.

Collect the current running-app listing without controlling the TV:

```sh
python3 tools/tv/verify_tv.py collect --device living-room --app-id YOUR_MOONLIGHT_APP_ID --out target/tv-verification/run-001
```

## Evidence required for a real TV test

A successful `ares-launch` exit code proves **only that the CLI accepted the request**. It does not prove that the app initiated or decoded a video stream.

To call a TV session verified, capture **independent** evidence: Moonshine host logs with timestamps, Moonlight's on-screen streaming statistics (resolution/codec/FPS/frame drops/host/network/decode metrics), and HDR on/off state where applicable. Preserve the capture and the exact tested Moonshine commit. Where possible, obtain client logs through a supported facility; do not invent remote access paths or expose device secrets.

Start by reproducing the known 4K60 HDR throughput issue under the deployed host, current upstream, and candidate branches on the **same TV settings**. Alternate A/B tests and separate capture/encode, sender queue, network, decoder, and display metrics. A short smoke is not a long-duration stability result.

## Safety and cleanup

This tool deliberately has no `stop` command: it cannot know whether an app started by a previous test has since become a user's active streaming session. End the session using Moonlight's normal interface after verifying that it still belongs to the test. Never kill arbitrary processes by name. No commands should contact the TV before user-authorized local testing.

Run offline command-safety tests with `python3 -m unittest discover -s tools/tv -p 'test_*.py'`.
