"""Studio agent — the embedded harness that lets OpenMontage run standalone.

Ported from learn-claude-code (s20 comprehensive, practical core set):
agent loop + tool dispatch + skill lazy-loading + context compaction +
error recovery + web approval gates. The model does the reasoning; this
package is only the vehicle.
"""
