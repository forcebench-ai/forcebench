# MCP study

What difference does an MCP server make to a coding agent doing Salesforce work? This study holds
the model, the agent and the model server still and adds one thing: the tools of
[Clientell's Salesforce MCP server](https://www.getclientell.com/salesforce-mcp/docs). The site
page is [forcebench.ai/studies/mcp](https://forcebench.ai/studies/mcp/); its numbers come from
`studies/mcp.json`, which this repository publishes and which holds aggregates only.

It has two parts, because an MCP server like Clientell's offers two kinds of help:

1. **Everyday work.** Salesforce's documentation, best practices and drafting tools, on the kind
   of task the benchmark is made of, where the prompt and files give the agent what it needs.
   Does the server help, or hurt, there?
2. **Work that depends on the org.** What the server is built for: knowing *your* org, its
   objects, fields, automation and permissions. Tasks whose answer depends on what is already in
   an org, with the server against the fair alternative, the org's metadata in the agent's
   workspace, as an engineer has it in their repository.

## Common design

- **Agent:** opencode 2.0.21, the [agent track](agent-track.md)'s, with its image, proxy, budgets
  (60 model requests and 262,144 output tokens per task; time is not budgeted), request fields
  (effort, sampling) and grading. The study's first DeepSeek sessions had an hour, as the agent
  track then did; those it stopped were answered again without it.
- **Models:** three served locally, each at its default effort: DeepSeek V4.1 Flash 1017
  (`deepseek-v4.1-flash-1017-native`, high), Qwen3.8 27B (`qwen3.8-27b-awq-int4`, medium) and
  Gemma 4 26B-A4B (`gemma-4-26b-a4b-nvfp4`, thinking on).
- **Order and load:** a model's arms run side by side, at the same concurrency, through the same
  LiteLLM proxy (`--via local`), so they share the model server under the same load.
- **Answers:** each task three times per arm (`--samples 3`).

## Part 1: everyday work

- **Tasks:** the lite subset, 60 tasks (four per suite, fifteen suites).
- **Arms:** opencode alone, and opencode with the server through its Code Mode
  (`--mcp clientell-codemode`, [MCP servers](agent-track.md#mcp-servers)); `make mcp-study-arms`.
  The study's first runs gave the server's tools as tools of their own (`--mcp clientell`); they
  are kept as a check arm, `mcp-tools` (see below). The Code Mode arms ran after the others,
  alone, at the pair's total concurrency (DeepSeek 8, Qwen 4, Gemma 2) so the model server
  carried the same load.
- **The server's org:** a Salesforce Developer Edition org made for this study, with Clientell's
  managed package installed (`04tQy000000CDJFIA4`) and connected to Clientell. Forcebench never
  logs in to it; only Clientell does. For these tasks it is just an org: the tasks don't depend on
  it, and the agent can deploy nothing to it.
- **What the agent is told:** the one sentence of the agent's note that says there is no network
  and no org becomes "There is no network access except the clientell tools, which reach
  Clientell's Salesforce MCP server and, through it, a Salesforce Developer Edition org; there is
  no org to deploy to or run tests in." It is not told to use them: like the skills in the
  [coding agent study](agent-track.md#reproducing-the-coding-agent-study), they are left to the
  agent.

## Part 2: work that depends on the org

- **The org:** a field service business, built for this study: sites, technicians, jobs and the
  parts used on them, with two before-save flows, a trigger and its handler, two validation
  rules, three permission sets and a custom metadata type
  ([orgs/base](../orgs/base/README.md#field-service-study-schema)). Its names and values are
  deliberately not the obvious ones (`Stage__c`, not `Status__c`; SLA hours of 4, 10, 36 and 120,
  not the usual 4, 8, 24 and 72), so remembering how such orgs usually look doesn't help.
  It is deployed to two orgs: the base grader org, where answers are graded (its automation runs
  on its own objects only, so no other suite sees it), and the Developer Edition org Clientell
  reads, where Clientell builds its graph of it.
- **Tasks:** 14 study tasks (`suites/org-context`, status `study`: never run by default, never on
  a leaderboard), written as tickets in business terms, without the org's API names: six Apex
  tasks graded by hidden tests in the grader org (put stale jobs on hold, complete jobs under the
  sign-off rule, an SLA due time from the custom metadata, a job's cost, a technician's open jobs,
  a region's urgent jobs), two metadata changes graded the same way (a hold reason with its rule
  and access, read-only access to part costs, both without dropping what the permission set
  already grants), and six questions about the org graded deterministically (who can see part
  costs, what renaming a stage would break, the SLA hours of a band, and three outcomes of saving
  a job, which need the order of execution).
- **Arms:** `make mcp-study-org-arms`, three side by side on `--subset study`:
  - **without:** opencode alone. It has only the prompt; it shows how far guessing gets.
  - **with the org's metadata** (`--org-source base`, [The org's metadata](agent-track.md#the-orgs-metadata)):
    the workspace is the org's SFDX project, the same `force-app` the two orgs were deployed
    from. Its note: "There is no network access and no Salesforce org; the metadata of the org
    this task is about, as retrieved from it, is in your working directory (an SFDX project:
    sfdx-project.json and force-app/)."
  - **with the server** (`--mcp clientell-org`): the same server, tools and Code Mode as part 1, its org now
    holding the same metadata. Its note: "There is no network access except the clientell tools,
    which reach Clientell's Salesforce MCP server and, through it, the org this task is about;
    there is no org to deploy to or run tests in."
- **Its runs are never published.** The tasks break the benchmark's rule that a prompt names
  everything the grader checks, on purpose; only the study's aggregates are.

## The server

- **Clientell's hosted server**, `https://mcp.clientell.ai/mcp`, with a workspace token from a
  trial account. It answers from its own service: what it does to produce an answer (search,
  its own models, the org's metadata graph) is part of what is measured.
- **Its tools:** the server (`clientell-salesforce` 0.2.0 when the study began) offers 37 tools.
  The agent gets the seven it marks read-only that concern Salesforce structure, documentation,
  guidance and drafts: `search_salesforce_metadata` and `clientell_start` (the org's metadata and
  an overview of it), `search_salesforce_docs`, `get_salesforce_best_practices` and
  `run_clientell_playbook` (Salesforce's documentation, Clientell's guides and playbooks), and
  `build_or_fix_salesforce_flow` and `author_salesforce_schema` (drafts of Flows, custom objects
  and fields, which deploy nothing). Not the account, billing, onboarding and connector tools
  (opencode approves every call unattended, and some change the account), the record-write
  proposals and their confirmation, the people and team-context tools, record merges, file
  generation, and reports and dashboards. The proxy shows the agent only these seven and refuses
  any other (`docker/agent/mcp/clientell.json`, `clientell-org.json`).
- **Its instructions:** the server sends about 2,000 characters of instructions when it
  connects (how to use its tools, a reminder never to answer org questions from memory), which
  opencode puts in the system prompt. They are passed unchanged, though they name some tools the
  agent isn't given.

## How the arms differ, and nothing else

Three things about opencode differ with the server, and each was checked:

- **The server's tools go through Code Mode, opencode's default.** opencode 2 gives every session
  one `execute` tool, in which the model writes JavaScript that calls the tools of a catalog; MCP
  tools are in that catalog unless a server asks otherwise. The study first gave them as tools of
  their own (`codemode: false`), the way most MCP clients give them. But `execute` stays in every
  arm either way, its description says tools are called inside it, and the models called the
  server's tools there, where they were not: in part 1, Gemma 397 times in 33 of 180 sessions,
  often never answering (29 sessions without an answer, against 13 without the server), DeepSeek
  120 times in 74, Qwen 8 times in 4. Through Code Mode those calls work, and the agent uses the
  server as opencode does out of the box (Gemma then called it in 42 sessions rather than 9, and
  ended without an answer as often as without it). The first runs are kept as a check arm,
  `mcp-tools`.
- **The session starts once the server's tools are there.** opencode fixes a session's tools when
  it starts and does not wait for MCP servers, so a session started at once never had the
  server's tools (seen in a smoke test: the server connected a few milliseconds after the first
  model request, and the session never got its tools, not even on later turns). With the server,
  the container starts opencode's server, waits until it reports the MCP server connected and 5
  seconds more (it reports connected before it has listed the tools and prompts), and runs the
  task on it. A session whose first request lacks the server's tools is re-run, never scored.
- **A User-Agent.** Clientell's web firewall refuses a request without one; the proxy passes
  opencode's.

Started either way, with a stand-in model and a stand-in MCP server that sends no instructions,
the two arms' first model requests are the same byte for byte (the system prompt, the other
tools' definitions, the request fields) but for the server's tools and the note's one sentence.
With Clientell's server, its instructions are the third difference. Through Code Mode the tool
list itself is the same byte for byte as without the server (checked on Gemma's runs): the
server's tools are a catalog in the system prompt, beside its instructions.

## What is measured

Per arm: the pass rate (a task's score is the mean over its answers; the rate is the mean over
tasks), with a 95% bootstrap interval over tasks, stratified by suite; output and input tokens,
model requests and time per session; sessions that ended without an answer.

Per model, for each pair of arms (the server against nothing; in part 2 also the metadata against
nothing, and the server against the metadata): the difference, **paired by task** over the tasks
both arms answered, with a 95% bootstrap interval over those tasks (10,000 resamples); the same
per suite, as a point only; how many tasks did better and worse. Across the three models: the mean
of their differences, tasks resampled jointly. In part 1, the check arm too: the server's tools as
tools of their own against nothing, and Code Mode against them.

How the agent used the server, from each session's raw records: sessions that called at least
one of its tools, calls per session and by tool, calls the server failed, time spent waiting for
it, the server's name and version as it reported them, and the pass rate of sessions that called
a tool against those that did not. That split is an observation, not an effect: a model reaches
for a tool on the tasks it finds hard.

## Keep in mind

- **One server, one agent, three models.** The result is about Clientell's server in opencode
  with these models on these tasks, not about MCP servers in general.
- **A hosted server changes without notice.** Each session records the name and version the
  server reported; a change during the study would show there.
- **The tasks reach Clientell.** Whatever the agent sends a tool (often the task's own words)
  goes to Clientell's service. The agent track uses public tasks only; nothing from the private
  pool is ever sent.
- **Part 2's org is small and made up.** Fourteen tasks on one org of four objects: a real org
  has far more to find, which can favour a search tool over reading files, or the other way.

## Reproducing it

```bash
make agent-image
# FORCEBENCH_CLIENTELL_TOKEN in .env; the model behind the LiteLLM proxy (provider `local`)
# Part 1
make mcp-study-arms MODEL=deepseek-v4.1-flash-1017-native EFFORT=high ARGS="--subset lite --samples 3 -c 4"
make mcp-study-arms MODEL=qwen3.8-27b-awq-int4 EFFORT=medium ARGS="--subset lite --samples 3 -c 2"
make mcp-study-arms MODEL=gemma-4-26b-a4b-nvfp4 EFFORT=on ARGS="--subset lite --samples 3 -c 2"
# Part 1's check arm, the server's tools as tools of their own
uv run forcebench run --agent opencode --mcp clientell --via local -m <id> -e <effort> --subset lite --samples 3 --no-grade
# Part 2, in a worktree (its runs are never published), once orgs/base/force-app is deployed to
# the base grader org (orgs/base/setup.sh) and to the org connected to Clientell
make mcp-study-org-arms MODEL=deepseek-v4.1-flash-1017-native EFFORT=high ARGS="--samples 3 -c 2"
make mcp-study-org-arms MODEL=qwen3.8-27b-awq-int4 EFFORT=medium ARGS="--samples 3 -c 2"
make mcp-study-org-arms MODEL=gemma-4-26b-a4b-nvfp4 EFFORT=on ARGS="--samples 3 -c 2"
# Grade each run, then aggregate both parts:
make grade ARGS="results/agent/runs/<run id>"
uv run forcebench study mcp --since <first run's id prefix> \
  --runs-dir results/agent/runs --runs-dir <worktree>/results/agent/runs
```

`--since` leaves out earlier runs, such as pilots. Only opencode runs made through a proxy,
without skills, are counted: of the lite subset for part 1, of the study tasks for part 2. Runs of
one arm add up.
