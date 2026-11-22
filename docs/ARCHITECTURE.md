# Architecture

Every node runs three concurrent services. Flask handles local submissions and read-only monitoring. A single sender thread owns outbound transmission. A TCP listener serves inbound connections, with at most 32 active handlers. The sender and receiver can operate independently on the same node.

| Stage | Implementation | Contract |
|---|---|---|
| Submission | netsense/client.py, netsense/api.py | The SDK and demonstration panel submit the same text and domain to the local REST API. MessageAdapter defines the interface for additional application adapters. |
| Classification | netsense/classifier.py, ml/train_model.py | Validate English text input size and domain, vectorize words and word pairs, score urgency and attach a version. |
| Enqueue | netsense/scheduler.py | A condition variable protects two FIFO deques, enrollment sequence and queue counts. Record acceptance in SQLite and return a unique ID. |
| Dispatch | netsense/agent.py | One worker chooses a waiting item. It completes its bounded send/acknowledge/retry cycle before selecting another. |
| Wire | netsense/protocol.py | Encode a length-prefixed JSON envelope with optional authentication. Read the exact number of bytes. |
| Receive | Connection in netsense/agent.py | Timestamp the decoded frame, validate fields, calculate available timing, commit once, acknowledge the ID. |
| Delivery and monitoring | netsense/storage.py, dashboard/ | Receiving applications read persisted messages by ID or filter. Flask serves the same records and aggregates to the polling dashboard. |

## Design decisions

The report’s socket interception is implemented at the integrated application boundary. A client explicitly supplies plaintext before the TCP send. Encrypted third-party applications and unrelated sockets are outside that boundary.

The scheduler makes selection atomic. Critical arrivals can pass normal items still waiting. An in-flight normal delivery completes first. Continuous critical arrivals can starve the standard queue. A normal wait average and maximum make that cost visible.

Each agent owns a separate SQLite database. Incoming message IDs and sender acknowledgement outcomes are distinct records, including during self-delivery. The dashboard can be closed or reopened while the receiver continues to record messages. A received message is available to an application through GET /api/messages or Client.received.

The operator configures the node, local bind address, peer and ports through JSON. Training happens offline. The runtime loads a trusted local joblib artifact once per agent. The project includes no kernel hook, router configuration or external inference service.
