# Artificial Intelligence Use Disclosure

**Project:** UUV Mission Planning and Energy Simulator  
**Release reviewed:** `v1` at commit `ec2dac5`  
**Development period represented in Git:** 24 April–23 July 2026  
**Disclosure prepared:** 23 July 2026  
**Document status:** AI-assisted draft pending author and advisor review

## Disclosure Statement

Generative artificial intelligence (AI) was used as a collaborative software-engineering and technical-writing tool during development of the UUV Mission Planning and Energy Simulator. The author reports using OpenAI ChatGPT with the GPT-5.5 and GPT-5.6 Sol models and using OpenAI Codex as a repository-aware coding agent.

AI assistance included requirements refinement, source-code review, implementation drafts, debugging, automated-test development and execution, user-interface and report refinement, documentation drafting, and release verification. The author established the research objectives, supplied the operational context, selected and approved model assumptions, reviewed outputs, directed revisions, and retained responsibility for the final software, analysis, and written material.

AI-generated material was treated as a draft or proposed change. It was not accepted solely because an AI system produced it. Changes were checked against the implemented code, automated tests, rendered application outputs, and Git history. The author made the final decisions concerning mission-model behavior, report content, user-facing presentation, and release readiness.


## Permission and Policy Status

- **Permission:** The capstone team received explicit permission from the Naval Postgraduate School Systems Engineering team to use generative AI in developing the application.
- **Approved scope:** The permission covers application development, programming-code generation and modification, and AI-assisted reasoning used to build the application.
- **Required condition:** The approved use requires a human-in-the-loop development process. The capstone team directed the work, reviewed proposed changes, evaluated outputs, required corrections, and retained decision authority.
- **Repository corroboration:** The Git history records an iterative pattern of implementation, correction, testing, report revision, and release verification. This history corroborates the reported human-in-the-loop workflow, although Git metadata alone cannot identify the human or AI origin of every changed line.

## AI Systems and Their Roles

### ChatGPT with GPT-5.5 and GPT-5.6 Sol

ChatGPT supported interactive problem definition and revision. The author used it to:

- translate operational goals and user observations into specific software changes;
- examine equations, assumptions, edge cases, and report language;
- compare proposed behavior with observed application behavior;
- draft and revise technical explanations and user documentation; and
- identify follow-on checks after implementation.

The model names are based on the author's reported use. Git does not record which model was active during an individual prompt, edit, or commit.

### Codex

Codex operated as a repository-aware software-engineering assistant. It could inspect files, search the codebase, edit source files, run commands and tests, review generated reports, and use Git. Codex supported:

- implementation and refactoring across the application, model, service, and reporting layers;
- diagnosis of calculation, user-interface, and report-export defects;
- creation and revision of automated tests;
- verification of dependencies, startup behavior, and release state;
- preparation of the `v1` release; and
- synchronization of the release with GitHub and the Hugging Face Space.

Codex was the working environment and agent; GPT-5.5 and GPT-5.6 Sol were models used through the workflow. They should not be counted as three independent authors.

## Scope and Attribution of AI-Produced Material

AI-generated or AI-revised material was incorporated into the software repository. The affected material includes portions of source code, automated tests, application and report text, the `README.md` file, user-documentation drafts, and this disclosure. Human-written and AI-assisted changes were sometimes combined in the same commit, and the repository does not contain reliable line-by-line authorship metadata. The repository and identified documentation should therefore be treated and labeled as AI-assisted works as a whole.

Release `v1` does not use ChatGPT, Codex, an OpenAI application programming interface (API), or another generative-AI model during normal execution. No OpenAI or generative-AI package appears in the release dependencies, and no runtime OpenAI integration appears in the source tree. Generative AI assisted development of the research software; it does not generate mission results when a user runs the released application.

## Human–AI Workflow

The project used an iterative, human-in-the-loop workflow:

1. The author stated the operational objective, constraint, defect, or desired presentation change.
2. The AI inspected the current repository and executable behavior before proposing a change.
3. The AI translated the request into a bounded code or documentation task.
4. The AI edited the working tree and reported the affected behavior.
5. The AI ran relevant automated tests and static or dependency checks.
6. The author reviewed the application, equations, reports, and user-facing results.
7. The author supplied corrections or approved the result.
8. The AI revised the implementation until the requested behavior and verification checks agreed.
9. Git recorded the accepted state in a commit.
10. At release, the same accepted commit was published to GitHub and Hugging Face.

## Repository History Reviewed

The repository contains:

- 29 commits by one recorded Git author;
- a linear history with no merge commits;
- approximately 90 days of recorded development;
- 27,263 inserted lines and 13,599 deleted lines across the full history;
- 57 tracked files in release `v1`;
- approximately 13,721 lines and 654 kilobytes in the release tree; and
- approximately 2.00 megabytes of cumulative added and removed text in commit patches.

The history shows four principal periods:

| Period | Commits | Work represented by commit history |
|---|---:|---|
| 24 April–1 May 2026 | 4 | Initial baseline, Hugging Face preparation, launch updates, and the `v3.2` milestone |
| 2–4 May 2026 | 8 | Geographic intelligence, surveillance, and reconnaissance (ISR) and user-interface fixes; model-logic rebuilding; payload and salinity changes; route and report updates; and the `v3.5-beta` candidate |
| 22–23 May 2026 | 11 | Power and temperature calibration, vehicle proxy revisions, Monte Carlo power sampling, low-current handling, report revisions, and the `v4` beta |
| 24 May–23 July 2026 | 6 | Repository cleanup, report theming, Hugging Face rendering stability, the `v1` workflow release, report-export repair, and stochastic current projection |

The Git author field identifies the person who committed the work.

## Human Oversight and Responsibility

The author retained responsibility for:

- defining the research question and intended operational use;
- choosing vehicle, mission, environmental, and sustainment assumptions;
- deciding whether proposed equations and stochastic behavior were suitable;
- reviewing the reasonableness of calculated results;
- visually evaluating the application and downloaded reports;
- directing corrections when the implementation did not meet the intended use;
- deciding what information belonged in the decision report;
- approving documentation and release content; and
- authorizing commits and publication.

The AI did not replace domain judgment. In particular, model outputs remain estimates whose usefulness depends on the selected inputs, assumptions, source data, and interpretation.

## Verification and Quality Controls

The development workflow used the following controls:

- source code, executable interfaces, tests, and configuration were treated as the implementation source of truth;
- proposed changes were reviewed as Git diffs before acceptance;
- automated tests were run after material model, interface, and reporting changes;
- calculation edge cases were added to the test suite when defects were identified;
- browser-visible and downloaded reports were reviewed for content and layout;
- dependency and startup checks were performed before release;
- generated random seeds and simulation details were retained where implemented for traceability; and
- release `v1` was checked against the local repository, GitHub, and the Hugging Face deployment.

These controls reduce error but do not prove that the software, equations, documentation, or AI suggestions are free of defects.

## Estimated AI Token Use

Git records accepted file changes, not AI prompts, responses, reasoning tokens, cached context, tool results, or discarded drafts. The repository contains no OpenAI usage export, invoice, or per-session token ledger. Exact AI consumption therefore cannot be reconstructed from Git.

The cumulative commit patches contain approximately 1,999,813 bytes of added and removed text. Using a planning conversion of four bytes per token gives approximately 500,000 artifact-equivalent tokens. This value is not the AI total. It represents only committed text churn and excludes repeated repository context, user prompts, AI explanations, command output, test logs, reasoning, revisions that were not committed, and ChatGPT conversations outside Git.

### Planning Estimate

| Estimate | Total tokens | Uncached input | Cached input | Output | Estimated credits |
|---|---:|---:|---:|---:|---:|
| Low | 5.0 million | 1.875 million | 1.875 million | 1.250 million | 1,195 |
| Central | 9.0 million | 3.375 million | 3.375 million | 2.250 million | 2,152 |
| High | 15.0 million | 5.625 million | 5.625 million | 3.750 million | 3,586 |

The published rate used for both GPT-5.5 and GPT-5.6 Sol was 125 credits per one million input tokens, 12.5 credits per one million cached input tokens, and 750 credits per one million output tokens. Because model choice, context size, reasoning, tools, retrieval, and caching affect consumption, this table is an order-of-magnitude estimate, not an invoice reconstruction.

## Estimated Cost

The most defensible single planning estimate is **approximately 9 million tokens, 2,152 ChatGPT credits, and of credit-equivalent AI use at approximately $143**.

- ChatGPT Pro is listed from `$100` per month. Approximately three months would equal at least `$300`.

This estimate excludes human labor, local computer use, network service, external hosting, and any other software subscriptions.

- Naval Postgraduate School Graduate Writing Center, “Generative AI,” accessed 23 July 2026: <https://nps.edu/web/gwc/generative-ai>
- Naval Postgraduate School Graduate Writing Center, “Citation and Disclosure,” accessed 23 July 2026: <https://nps.edu/web/gwc/citation-disclosure>
- Naval Postgraduate School, “Interim Guiding Principles for Use of Generative Artificial Intelligence (AI) Tools,” 15 March 2023: <https://nps.edu/documents/106660594/140848999/Interim-Guidance-on-Generative-AI-3.15.23%2BMemo.pdf/9cde404a-b369-d959-ef26-74832a7b429b>
- Naval Postgraduate School Generative AI Task Force, “NPS Guidance on Disclosing Generative AI Use in Academic Work,” 18 June 2024: <https://nps.edu/documents/111693070/151421299/Disclosing%2BGenerative%2BAI%2BUse%2BNPS%2B2024.06.20.pdf/307848a6-73f9-a56a-da2e-dcf1f554ff31>
- Naval Postgraduate School Graduate Writing Center, “Responsible Use,” accessed 23 July 2026: <https://nps.edu/web/gwc/responsible-use>

- OpenAI, “Pricing,” ChatGPT Work and Codex documentation, accessed 23 July 2026: <https://learn.chatgpt.com/docs/pricing>
- OpenAI, “Codex for Students,” credit-equivalence information, accessed 23 July 2026: <https://developers.openai.com/community/students>
