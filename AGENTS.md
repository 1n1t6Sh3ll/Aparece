# PowerLens team
Use the project-team skill. One project manager maintains priorities, dependencies, and acceptance criteria and resolves claim conflicts with the human. The project manager can also orchestrate agents.
Read coordination/BOARD.md. Claim before editing; stay within scope; submit evidence for independent review. Keep code and updates short. Use separate workspaces for concurrent implementation.

Follow the project-team skill's human merge gate: required checks, independent review, affected documentation updates, and explicit human approval of the exact revision before every merge. No direct pushes to main or bypassing protections. Keep handoffs concise, with evidence links. GitHub enforcement is pending until configured and verified.


# Source attribution and simple implementation

When copying or adapting external code, record the source URL, author/project, version or commit when available, license, affected files, and modifications in THIRD_PARTY_NOTICES.md. Keep any required copyright and license notices with the code or distribution. Attribution alone does not grant permission: if reuse terms are missing or incompatible, do not copy; find a compatible alternative or ask the human. Cite research and documentation in the relevant task or design decision. Distinguish dependencies, copied code, and conceptual references.

Choose the simplest maintainable solution that meets acceptance criteria. Reuse suitable existing components, avoid duplicate logic and speculative abstractions, and add dependencies only when their benefit justifies their cost. Do not claim a solution is optimal without evidence; measure performance when it matters. Never sacrifice correctness, necessary security, or meaningful checks for fewer lines or tokens.

