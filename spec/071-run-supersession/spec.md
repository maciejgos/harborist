# Run supersession

An operator supplies replacement intent and a reason. Shipyard freezes a new contract and explicitly links the original Run to the replacement. The original is retired under the same execution safeguards as cancellation. The service queues the replacement as an independent Run. Repeating the service request with the same replacement is safe.

Existing GitHub PRs stay open for human handling. Local Run status identifies supersession and shows the replacement Run ID. The replacement starts from its own base and earns its own verification.
