# Faculty demonstration

Prepare two running nodes using the pair procedure in README.md. Keep A's sender console and B's receiver monitor visible. On one laptop use separate browser windows. Record whether you used loopback or two physical machines.

## 1. Routine message

On A, choose the routine handover example and press **Send**. Read the returned NORMAL label and short ID. On B, filter priority to NORMAL. Open the green row and match the ID, full content and sender. The enqueue, transmission and arrival timestamps show where each measurement was taken.

## 2. Critical message

Clear B's filter. On A, send the emergency patient example. Open its red CRITICAL row on B. Explain that the trained model scored the text before the scheduler saw it. A single message demonstrates classification and delivery. Ordering becomes visible when several messages are waiting.

## 3. Mixed traffic and scheduling

Use the generated pair's 80 ms demo spacing. On A open **Traffic simulator**, choose 12 messages, a 25% critical mix, 5 ms arrivals and 80 ms pacing. Click **Start traffic**. On B, inspect the newest receipts and compare their enqueued and received times. The emergency examples can pass routine examples that were already waiting. Within each class, earlier admissions go first. The first routine message may already have left before a critical message arrives. The live table shows newest first, so read a batch from bottom to top for dispatch order.

For a controlled policy comparison, run:

```powershell
python -m scripts.compare --output my-comparison.json
```

The output lists delivery order (C or N), receiver metrics and acknowledgement counts. Use avg_wait to explain the queue effect. Both policies use the same deterministic input sequence and the same 25 ms service spacing. A different run can give different times.

## 4. Traffic analytics

Show critical and normal counts, distribution, messages per minute, network p95 and maximum normal queue wait. Open **Network nodes** on A to show outbound acknowledgements. Return to B for receipt metrics. Point out the visible cost to waiting normal traffic. Refresh the browser to show retained receipts. To demonstrate persistence, stop B after deliveries finish, restart with its original config, and match an earlier ID.

## 5. Physical LAN verification

Start the two agents on separate machines using the LAN setup in README.md. Send a distinctive routine sentence from A, then the fire sample. On B, copy each full ID from its details. Query the IDs on A's outbound endpoint and B's received endpoint. Repeat in reverse. Record the actual evidence below when running the physical demonstration.

| Item | Record at the venue |
|---|---|
| Machines and addresses | A's node/IPv4 and B's node/IPv4 |
| Connectivity | A to B port 7202, B to A port 7201 |
| A to B | ID, expected content, observed label, received time, A's outcome |
| B to A | ID, receiving node, receipt, B's outcome |
| Timing basis | Clock source/status on both machines or remote latency unavailable |
| Result | Date, operator, observed pass or specific failure |

A concise explanation for the evaluator: “Our application submits text to NetSense. The model scores urgency, and one sender chooses a critical message whenever one is waiting. The other machine commits the message and acknowledges the same ID. Those recorded events drive the dashboard.”
