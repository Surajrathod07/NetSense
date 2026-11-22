# NetSense
**Intelligent Message Priority System for Critical Network Communication**

Suraj Rathod · Vishu Attri · Prabal Singh Bais  
Department of Information Technology, MIT Academy of Engineering, Alandi, Pune  
Data Communication · 2026–2027 · Guide: Mr. Shivaji Patil

NetSense runs a sender, receiver and monitoring dashboard on each computer. Submit an English text message through the dashboard, Python client or local REST API. A trained TF-IDF classifier assigns its priority. One worker serves waiting critical messages first, sends each message over TCP, and records delivery after the receiver commits it to SQLite and acknowledges its ID.

## Start on Windows

1. Install 64-bit CPython **3.12** using the Windows installer from python.org. Include the Python launcher. The supplied dependency versions were exercised with Python 3.12.
2. Extract the archive and open the **NetSense** folder containing `run.py` in VS Code. Open a PowerShell terminal there.
3. Run the following commands. Installation requires internet access. Training, sending and monitoring run locally.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If script activation is restricted, run the commands with `.\.venv\Scripts\python.exe` in place of `python`. The archive includes the CSV and a trained model. Retraining from the supplied CSV recreates both the model and its evaluation metadata. To rebuild the synthetic CSV itself, run `python -m ml.build_data` first.

Open **http://127.0.0.1:5000**. Open **Send message**, select a sample and click **Send message**. Open **Live monitoring** to inspect its receipt. The same agent sends over a real loopback TCP connection and displays the committed receipt. Use Ctrl+C to drain queued work and stop. The database lives at `runtime/node.sqlite`.

On Linux or macOS, create the environment using `python3.12 -m venv .venv`, activate with `source .venv/bin/activate`, then use the same install and startup commands.

## Present from one laptop

1. Open Network nodes and test the configured TCP peer. Local demo uses the same machine as sender and receiver.
2. Open Send message, select the hospital alarm and send it. In Live monitoring, open the message ID to see its score, timestamps and delivery latency. Repeat with the handover sample.
3. In Traffic simulator, start a 32-message mixed run with 15 ms arrivals and 120 ms pacing. Inspect the waiting queues and received order. Stop generation to let accepted work drain.
4. Click Compare FCFS and priority. Both policies replay the same classified input under a fixed service time. Compare critical delay **and** maximum normal wait. These chart values are simulated. The two-process script below measures actual local TCP deliveries.
5. Open Analytics for measured delivery and queue timing. ML model shows the separately evaluated synthetic test set. Changes to the threshold last until restart or retraining. Message corrections enter SQLite and can be included by an explicit retraining run. Administrative actions use the dashboard on localhost.

The console shows up to 500 recent receipts in Live monitoring. CSV export covers the full receiver log. The classic single-page dashboard is preserved at `/classic`.

## Run two agents on one computer

Generate separate configurations, ports and databases. In two terminals with the virtual environment active, start B first and then A.

```powershell
python -m scripts.configure_pair
# Terminal 1
python run.py --config config/node-B.json
# Terminal 2
python run.py --config config/node-A.json
```

A's dashboard is **http://127.0.0.1:5001**. B's is **http://127.0.0.1:5002**. Send from A and look for the message on B. The generated pair uses an 80 ms inter-message demonstration pause. Set `demo_delay_ms` to zero for ordinary operation.

## Run on two Windows computers

1. Connect A and B to the same trusted private LAN. Install the project and dependencies on each. Run `ipconfig` on each and note the IPv4 addresses of their active LAN adapters.
2. Generate the configurations on each machine with the same A and B addresses. The addresses below are examples. For previously generated files, edit the corresponding fields directly. The generator preserves existing files.

```powershell
python -m scripts.configure_pair --a 192.168.1.21 --b 192.168.1.22
```

3. On B, allow incoming TCP **7202** from A on the private network profile. For return traffic from B to A, allow inbound TCP **7201** on A. An administrator can add these scoped rules locally on the indicated machine. Replace the example addresses.

```powershell
# On B
New-NetFirewallRule -DisplayName "NetSense from A" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 7202 -RemoteAddress 192.168.1.21 -Profile Private
# On A
New-NetFirewallRule -DisplayName "NetSense from B" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 7201 -RemoteAddress 192.168.1.22 -Profile Private
```

4. For signed frames and acknowledgements, set the same private value for `NETSENSE_SECRET` in both launch terminals, for example `$env:NETSENSE_SECRET = Read-Host "Enter the shared demo secret"`. Message contents travel in plaintext. Use synthetic demonstration traffic.
5. Start B with `python run.py --config config/node-B.json`. On A run `Test-NetConnection 192.168.1.22 -Port 7202`. Check that `TcpTestSucceeded` is true, then start A with `python run.py --config config/node-A.json`.
6. Use the local dashboard on each computer. Send a message from A. On B, open its details and match the ID, content and sender. Repeat in reverse. Only the TCP receiver needs LAN exposure. The Flask dashboard and submission API stay on loopback. Binding a service to `0.0.0.0` exposes it through all available IPv4 interfaces.
7. Remote one-way time is hidden initially. Check clock synchronization on **both** computers (on Windows, `w32tm /query /status`). Enable `clocks_synced` on the receiver and restart only when the clocks’ uncertainty is acceptable for the measurements. Queue waiting time is available independently. Both nodes may receive, so configure each as needed.

## SDK and receiving interface

From the project directory, using the default single-node configuration:

```python
from netsense.client import Client

client = Client("http://127.0.0.1:5000")
receipt = client.send_message("Fire reported in block C. Evacuate immediately.", "disaster")
print(receipt["id"], receipt["label"])
# Run after delivery, against the receiving node's local API.
print(client.received(id=receipt["id"]))
```

The HTTP equivalent in PowerShell is:

```powershell
$body = @{text="Please submit the weekly supply report."; domain="disaster"} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:5000/api/messages/send' -Method Post -ContentType application/json -Body $body
Invoke-RestMethod 'http://127.0.0.1:5000/api/messages'
```

## Verification and presentation

```powershell
python -m unittest discover -v
python -m scripts.compare --output my-comparison.json
```

The comparison starts fresh agents and databases for each policy, checks received IDs and contents, then restarts each receiver and checks persistence. For optional browser automation, install `playwright` in a development environment, run `python -m playwright install chromium`, then `python -m scripts.console_check`.

| File | Use |
|---|---|
| docs/DEMO_GUIDE.md | Five faculty demonstrations and physical LAN acceptance record |
| docs/ARCHITECTURE.md | Follow one message across the modules |
| docs/TECHNICAL_DOCUMENTATION.md | Protocol, API, training, timing and configuration reference |
| docs/TEST_REPORT.md | Observed model, scheduling, transport and browser results |
| ml/model_metadata.json and docs/benchmark.json | Machine-readable measurements |

**Scope.** Applications integrate explicitly through an adapter, the SDK or REST. Strict priority controls a single sender's backlog. Each agent has one configured outbound peer and can accept messages from multiple permitted peers. The synthetic English classifier is an educational prototype. Real safety-critical deployment needs separate validation.

**Troubleshooting.** A missing model or metadata file requires `python -m ml.train_model`. A bind error usually means that another node owns the configured port or the local address belongs to another machine. A queued ID followed by failed attempts points to peer address, firewall, listener or secret mismatch. Look at the sender activity and the receiver's dashboard separately. Use one database file per running agent.
