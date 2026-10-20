# MCP study

What difference does an MCP server make to a coding agent doing Salesforce work? This study holds
the model, the agent, the tasks and the model server still and adds one thing: the tools of
[Clientell's Salesforce MCP server](https://www.getclientell.com/salesforce-mcp/docs). The site
page is [forcebench.ai/studies/mcp](https://forcebench.ai/studies/mcp/); its numbers come from
`studies/mcp.json`, which this repository publishes and which holds aggregates only.

## Design

- **Question:** does a model in opencode pass more Salesforce tasks with Clientell's MCP server
  than without it?
- **Arms:** per model, opencode 2.0.21 alone and opencode 2.0.21 with the server
  (`--mcp clientell`, [MCP servers](agent-track.md#mcp-servers)). Nothing else differs (below).
- **Models:** three served locally, each at its default effort: DeepSeek V4.1 Flash 1017
  (`deepseek-v4.1-flash-1017-native`, high), Qwen3.8 27B (`qwen3.8-27b-awq-int4`, medium) and
  Gemma 4 26B-A4B (`gemma-4-26b-a4b-nvfp4`, thinking on).
- **Tasks:** the lite subset, 60 tasks (four per suite, fifteen suites), each answered three
  times per arm: one run of one answer per task, then a run of two more. Graded like any agent
  run, in the Forcebench sandbox.
- **Order and load:** a model's two arms run side by side (`make mcp-study-arms`), at the same
  concurrency, through the same LiteLLM proxy (`--via local`), so they share the model server
  under the same load. One model at a time.

## The server

- **Clientell's hosted server**, `https://mcp.clientell.ai/mcp`, with a workspace token from a
  trial account. It answers from its own service: what it does to produce an answer (search,
  its own models, the org's metadata graph) is part of what is measured.
- **Its org:** a Salesforce Developer Edition org made for this study, with Clientell's managed
  package installed (`04tQy000000CDJFIA4`) and connected to Clientell. Forcebench never logs in to
  it; only Clientell does. It is not the org answers are graded in: its metadata is a standard
  org's, without the grader's `Shipment__c` schema and seed data, and the agent can deploy
  nothing to it.
- **Its tools:** five of the server's tools, the Salesforce ones that read or draft and bear on
  the suites' subjects: `search_salesforce_metadata`, `get_salesforce_best_practices`,
  `search_salesforce_docs`, `build_or_fix_salesforce_flow` and `generate_salesforce_org_report`.
  Not its account, billing, onboarding and connector tools (opencode approves every call
  unattended, and some change the account), nor those for people, team context, record merges,
  reports and dashboards, which no suite asks about. The proxy shows the agent only these five
  and refuses any other (`docker/agent/mcp/clientell.json`).
- **What the agent is told:** the one sentence of the agent's note that says there is no network
  and no org becomes "There is no network access except the clientell tools, which reach
  Clientell's Salesforce MCP server and, through it, a Salesforce Developer Edition org; there is
  no org to deploy to or run tests in." It is not told to use them: like the skills in the
  [coding agent study](agent-track.md#reproducing-the-coding-agent-study), they are left to the
  agent.

## What else stays the same

The image, the proxy, the budgets (60 model requests, 262,144 output tokens, an hour per task),
the request fields (effort, sampling) and the grading are the agent track's. Two things about
opencode differ between the arms, and both were checked:

- **The server's tools are tools of their own.** opencode 2 gives MCP tools to the model through
  its Code Mode by default: the model writes JavaScript that calls them through one `execute`
  tool. They are given as ordinary tools instead (`clientell_search_salesforce_docs` and so on),
  the way most MCP clients give them, so the study measures the server rather than how well a
  model scripts Code Mode.
- **The session starts once the server is connected.** opencode fixes a session's tools when it
  starts and does not wait for MCP servers, so a session started at once never had the server's
  tools (seen in a smoke test: the server connected a few milliseconds after the first model
  request, and the session never got its tools, not even on later turns). With the
  server, the container starts opencode's server, waits until it reports the MCP server
  connected, and runs the task on it. A session whose first request lacks the server's tools is
  re-run, never scored.

Started either way, with a stand-in model and a stand-in MCP server, the two arms' first model
requests are the same byte for byte (the system prompt, the other tools' definitions, the
request fields) but for the server's tools and the note's one sentence.

## What is measured

Per arm: the pass rate (a task's score is the mean over its answers; the rate is the mean over
tasks), with a 95% bootstrap interval over tasks, stratified by suite; output and input tokens,
model requests and time per session; sessions that ended without an answer.

Per model: the difference with the server minus without, **paired by task** over the tasks both
arms answered, with a 95% bootstrap interval over those tasks (10,000 resamples); the same per
suite, as a point only (four tasks each); how many tasks did better and worse. Across the three
models: the mean of their differences, tasks resampled jointly.

How the agent used the server, from each session's raw records: sessions that called at least
one of its tools, calls per session and by tool, calls the server failed, time spent waiting for
it, the server's name and version as it reported them, and the pass rate of sessions that called
a tool against those that did not. That split is an observation, not an effect: a model reaches
for a tool on the tasks it finds hard.

## Keep in mind

- **One server, one agent, three models.** The result is about Clientell's server in opencode
  with these models on these 60 tasks, not about MCP servers in general.
- **A hosted server changes without notice.** Each session records the name and version the
  server reported; a change during the study would show there.
- **The tasks reach Clientell.** Whatever the agent sends a tool (often the task's own words)
  goes to Clientell's service. The agent track uses public tasks only; nothing from the private
  pool is ever sent.
- **The connected org is not the grader's.** Tools that read the org see a standard Developer
  Edition org, not the grader's schema; a task's own files and prompt give the agent what it
  needs, with or without the server.

## Reproducing it

```bash
make agent-image
# FORCEBENCH_CLIENTELL_TOKEN in .env; the model behind the LiteLLM proxy (provider `local`)
make mcp-study-arms MODEL=deepseek-v4.1-flash-1017-native EFFORT=high ARGS="--subset lite -c 4"
make mcp-study-arms MODEL=deepseek-v4.1-flash-1017-native EFFORT=high ARGS="--subset lite --samples 2 -c 4"
make mcp-study-arms MODEL=qwen3.8-27b-awq-int4 EFFORT=medium ARGS="--subset lite -c 2"
make mcp-study-arms MODEL=qwen3.8-27b-awq-int4 EFFORT=medium ARGS="--subset lite --samples 2 -c 2"
make mcp-study-arms MODEL=gemma-4-26b-a4b-nvfp4 EFFORT=on ARGS="--subset lite -c 2"
make mcp-study-arms MODEL=gemma-4-26b-a4b-nvfp4 EFFORT=on ARGS="--subset lite --samples 2 -c 2"
# Grade each run, then aggregate the study's runs:
make grade ARGS="results/agent/runs/<run id>"
uv run forcebench study mcp --since <first run's id prefix>
```

`--since` leaves out earlier runs, such as pilots. Only opencode runs of the lite subset made
through a proxy, without skills, are counted; runs of one arm add up.
