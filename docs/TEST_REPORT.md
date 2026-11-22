# Verification results

The 10 automated tests in tests/ passed on Python 3.12. They cover classification across three domains, scheduling and FIFO, concurrent admission, framing, malformed data, disconnects, retries, clock handling, persistence, all nine HTTP routes, operator controls, traffic generation and CSV exports.

## Local TCP comparison

The script started separate sender and receiver processes per policy. Each policy delivered and acknowledged all 32 messages. Each receiver was restarted to confirm persistence. Network conditions and host scheduling can change the timings.

| Policy | Critical mean wait (ms) | Normal mean wait (ms) | Maximum normal wait (ms) |
|---|---:|---:|---:|
| fcfs | 421.4 | 371.9 | 743.5 |
| priority | 92.5 | 479.8 | 766.5 |

## Classifier

The 360 synthetic examples use 60 base scenarios. Related examples stay together across the 216/72/72 train, validation and test split. The selected logistic regression model at threshold 0.45 classified 66 of 72 held-out examples correctly. All 36 critical examples were detected. Six normal examples were flagged as critical.

## Remaining verification

Two physical computers were unavailable. Follow the LAN acceptance steps in DEMO_GUIDE.md at the venue. The nine-page browser acceptance script is included. This runtime blocked Chromium startup and the separate browser could not reach the local Flask port. HTTP integration checks and JavaScript syntax checks passed.
