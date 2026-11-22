# Technical reference

## Classifier and evidence

The generated CSV contains 360 balanced educational examples. Each domain has 10 critical and 10 normal base scenarios, each rendered at six locations. A scenario identifier groups related texts. A seeded, domain-and-label stratified split assigns entire scenarios to training, validation or testing in a 60/20/20 ratio. The effective test set is 12 distinct scenarios with six variations each. Domain and location metadata are never supplied as separate prediction features.

Text normalization collapses whitespace and lowercases the message. TF-IDF tokenization handles punctuation, forms unigrams and bigrams, applies sublinear term frequency, smoothed inverse document frequency and L2 normalization. Each candidate fits its vectorizer solely on training data. A joblib pipeline preserves the vocabulary, weights and estimator together.

Multinomial Naive Bayes and logistic regression score the probability of CRITICAL. Linear SVM uses the signed margin toward CRITICAL. Classes are ordered CRITICAL, NORMAL, so its binary decision margin is negated. The stored score always refers to CRITICAL, including when a message is classified NORMAL.

Validation selects thresholds using a critical precision floor of 0.75, then critical recall and precision. Ties within a candidate use the threshold nearest its ordinary decision boundary. Across candidates a mean inference budget of 5 ms and a preference for logistic regression break quality ties, followed by speed. The winning validation choice is evaluated once on held-out data. The numeric threshold and version accompany the model. To change the probability threshold candidates:

```shell
python -m ml.train_model --thresholds 0.35 0.40 0.45 0.48 0.50
```

Candidate validation confusion matrices, training time and inference time appear in ml/model_metadata.json. Matrix rows are actual labels, columns predicted labels, each ordered CRITICAL, NORMAL. Test metrics belong to the selected model. An English text classifier can miss unfamiliar wording, negation or context. Domain experts would need to supply independently labelled real messages before assessing deployment suitability.

## Scheduling, protocol and storage

Both FIFO queues share one condition lock. Each item holds a monotonic enqueue reference and sequence number. Priority mode takes the head of the critical deque whenever available. FCFS compares the two head sequence numbers. Submission capacity is 2,048 waiting messages. A full queue returns HTTP 503. The worker processes one delivery at a time. A failed attempt opens a fresh connection after bounded backoff, keeping the same message ID. Optional demo spacing is applied after processing an item.

Frames consist of a four-byte unsigned big-endian length followed by that many UTF-8 JSON bytes. The envelope has a body object and a mac string. With NETSENSE_SECRET configured, the MAC is HMAC-SHA256 over Python's canonical JSON body with sorted keys, compact separators, default ASCII escaping and finite numbers. The default unsigned mode uses an empty MAC. Both directions use the same framing and key.

The version-1 message body contains id (canonical UUID), sender, text, domain, label, score, score_kind, model_version, classification_ms, enqueued, sent and wait_ms. The ACK body contains id and status (received or duplicate). A new socket per attempt simplifies reconnects. A receiver also accepts adjacent frames on a single connection. Partial reads loop until the length is satisfied. Invalid input closes that connection and is logged. Each operation is bounded by a configured socket timeout. HMAC authenticates peers holding the key. TCP payloads are readable on the wire.

| SQLite table | Contents and lifecycle |
|---|---|
| messages | One row per committed incoming UUID, with original JSON, sender, class, domain, enqueue and transmission data in the payload, indexed arrival time, wait, network and combined estimates. |
| outbound | Local acceptance, label, queued/acknowledged/failed/interrupted outcome and wait. A final failed status means delivery could not be confirmed. The peer may already have committed if the final ACK was lost. |
| activity | Ordered event sequence, wall time, category and detail for lifecycle, scheduling, connections, delivery, retries or rejection. |

Each operation uses a parameterized SQLite connection and a short transaction. WAL allows concurrent readers. Receiver deduplication and receipt logging complete before ACK. Conflicting identity reuse is rejected. A graceful shutdown drains accepted items. Pending queue contents live in memory. On next startup unfinished local submissions are marked interrupted, so abrupt process loss can require application resubmission. Only one live agent may own a database.

## Timing

| Field | Measurement and interpretation |
|---|---|
| classification_ms | Sender monotonic duration of local inference. |
| wait_ms | Sender monotonic time from admission to dequeue. Includes acceptance bookkeeping while the scheduler lock is held. |
| sent, received | UTC epoch seconds. The sender samples immediately before framing and sending an attempt. The receiver samples after decoding and authenticating the complete frame, before persistence. |
| latency_ms | 1000 × (received − sent). Includes encoding, decoding and OS scheduling. Available on loopback or after operator-confirmed clock synchronization. Negative differences are suppressed. |
| total_ms | wait_ms + latency_ms when latency is available. This estimate excludes classification, post-dequeue connection setup, prior failed attempts, database commit and return ACK time. |

Reports use arithmetic means and NumPy's linear-interpolation 95th percentile over available readings. A dash or JSON null means unavailable. Positive clock skew also distorts one-way timing. The program cannot certify synchronization from the two timestamps. Queue priorities affect time spent waiting at the sender. Switching policies does not guarantee faster transit after a send begins.

## HTTP interface

Responses wrap success in a data field and errors in an error field. POST bodies must be JSON objects. Accepted sends return 202 with a classification and correlation ID. Acknowledgement can be checked later on the sender.

| Method and path | Input or result |
|---|---|
| POST /api/messages/send | text (1–4096 UTF-8 bytes) and domain (hospital, disaster, factory). |
| GET /api/outbound/{id} | Sender-side outcome by ID. Unknown IDs return 404. |
| GET /api/messages | Newest-first received records. Exact id, label, sender, domain; content substring q; since and until epoch seconds; limit 1–500, offset ≥0. |
| GET /api/metrics | Class counts, means, network p95, queue maximums, 15 minute bins, sender outcomes. |
| GET /api/system/status and /api/health | Live worker and receiver state, database probe, per-session queue counts, public configuration. |
| GET /api/model/status | Loaded model, split sizes, threshold, candidate validation and held-out results. |
| POST /api/test/load | count from 1 to 48; repeats three normal samples and one critical sample, each submitted to the classifier. On saturation the response includes IDs already accepted. |
| GET /api/activity | Latest 50 event records, newest first. |

The UI polls every two seconds after the previous poll completes. It paginates messages, supports text, sender, priority, domain and start-time filters, and displays full message fields on demand. Recent activity and metrics come from the local node. Queue counters reset on restart, while receipt metrics and delivery history persist.

## Configuration

Use config/config.json for the default node and --config for another file. Set node, listen_host/tcp_port, peer_host/peer_port, web_host/web_port and database separately. Set mode to priority or fcfs. timeout is in seconds and retries counts *additional* attempts. max_frame is the envelope byte limit. demo_delay_ms adds visible queue pressure between transmissions, with a default of zero. clocks_synced controls remote wall-clock estimates. Keep the dashboard on loopback since it includes submission controls. The receiver validates signed frames when a shared key is configured. SQLite and joblib files are local trusted project data.
