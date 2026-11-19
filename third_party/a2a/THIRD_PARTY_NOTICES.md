# Third-party reference code and fixtures — Apache License 2.0

These files were copied **verbatim** from the following open-source upstream
repositories for offline protocol review and regression tests. They have
not been deployed or used to execute third-party agents.

| Local path | Upstream pinned source | License |
| --- | --- | --- |
| `specification/a2a.proto` | [A2A proto](https://github.com/a2aproject/A2A/blob/5f931b8a25fe66789f987ec4a55fc16ee9fe41ee/specification/a2a.proto) | Apache-2.0 |
| `fixtures/air_ticketing_agent.json` | [A2A sample card](https://github.com/a2aproject/a2a-samples/blob/1d7b7be24971c60fe5019182c1d26b7e9ae137ed/samples/python/agents/a2a_mcp/agent_cards/air_ticketing_agent.json) | Apache-2.0 |
| `fixtures/currency_agent.json` | [A2A sample card](https://github.com/a2aproject/a2a-samples/blob/1d7b7be24971c60fe5019182c1d26b7e9ae137ed/samples/python/agents/adk_currency_agent/src/currency_agent/agent_card.json) | Apache-2.0 |

The upstream full license is retained as `LICENSE`. Retain source and
license notices when redistributing. No upstream code files were modified;
our separate preflight validator is original code in `automation/`.

**Important:** The sample cards use `localhost` HTTP addresses and/or
legacy A2A card shapes. They are **negative regression fixtures**, not
approved production identity records. Never publish them as live agents.

The proto imports Google common protos and may need additional dependencies
to compile; vendoring it is a **pinned reference**, not a claim that full
A2A protocol transport or compliance is implemented.
