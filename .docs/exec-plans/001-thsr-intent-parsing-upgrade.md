# THSR Intent Parsing Upgrade

## Summary

Upgrade the THSR flow from route-only parsing into a structured intent pipeline. For every THSR query, call the local LLM first to extract a normalized intent object, then validate and normalize that object in code before querying the parsed PDF timetable. Extend the deterministic lookup layer to support natural-language dates and departure-time preferences, especially queries like `明天南港到嘉義大約下午3:00的高鐵班次？`, interpreted as trains departing at or after the requested time.

## Steps

1. Add a THSR intent schema in `/home/bwang/workspace/web_search/transport_helpers.py` that represents `origin`, `destination`, `travel_date`, `departure_time`, `time_preference`, and `parse_status`. Keep the existing route regex logic available as deterministic fallback when LLM output is invalid. This schema becomes the boundary between LLM parsing and timetable lookup.
2. Add an LLM-backed intent extraction function in `/home/bwang/workspace/web_search/transport_helpers.py`, using the same local Ollama model but with a strict JSON-only prompt for THSR queries. The prompt should require normalized Traditional Chinese station names, explicit date semantics, 24-hour departure time when available, and an enum for time preference. This step depends on step 1.
3. Add deterministic post-validation and normalization in `/home/bwang/workspace/web_search/transport_helpers.py`: validate stations against `THSR_STATIONS`, normalize relative dates such as `今天`, `明天`, `後天` into concrete dates, normalize explicit dates such as `6/15`, and convert phrases like `下午3:00` to `15:00`. If the LLM omits or corrupts fields, either repair from the raw query using local rules or fall back to the existing route parser. This step depends on steps 1-2.
4. Refactor `build_thsr_reply()` in `/home/bwang/workspace/web_search/transport_helpers.py` to consume the structured intent instead of directly calling `extract_route_stations()`. Preserve the early-return behavior in `/home/bwang/workspace/web_search/main.py`, but route THSR questions through: intent extraction -> validation/normalization -> timetable lookup -> response formatting. This step depends on step 3.
5. Extend `_find_next_thsr_trains()` in `/home/bwang/workspace/web_search/transport_helpers.py` to accept date and time constraints. For the agreed semantics, `大約下午3:00` should mean departures at or after `15:00`, ordered by nearest qualifying departure. Keep the current "from now onward" behavior only when no explicit date/time preference is present. This step depends on step 4.
6. Add date handling boundaries to the lookup layer in `/home/bwang/workspace/web_search/transport_helpers.py`: when the requested date is outside the currently published timetable’s effective period or cannot be trusted because of special schedules, return a precise fallback message explaining that the timetable source is static and the user should verify on the official THSR site. This step depends on step 5.
7. Expand regression coverage in `/home/bwang/workspace/web_search/tests/test_transport_helpers.py`. Add tests for LLM intent post-validation, relative dates, explicit month/day dates, `下午3:00` normalization, and end-to-end replies for cases like `明天南港到嘉義大約下午3:00的高鐵班次？`. Mock time and mock LLM output so tests stay deterministic. This step can start in parallel with steps 3-5 once the schema is stable.
8. Add a focused end-to-end smoke check from `/home/bwang/workspace/web_search/main.py` after the refactor, using the existing CLI harness to verify representative queries for current-day nearest departures, future-date departures, and explicit time-constrained departures. This step depends on steps 4-7.

## Relevant Files

- `/home/bwang/workspace/web_search/main.py` — preserve the top-level pipeline and THSR early-return, but ensure THSR queries now pass through the structured intent path before reply generation.
- `/home/bwang/workspace/web_search/transport_helpers.py` — primary implementation surface for intent schema, LLM extraction, normalization, timetable filtering, fallback behavior, and user-facing THSR reply composition.
- `/home/bwang/workspace/web_search/tests/test_transport_helpers.py` — extend with deterministic regressions for date parsing, time parsing, LLM output validation, and end-to-end THSR query handling.

## Verification

1. Run `python -m unittest discover -s tests -p 'test_transport_helpers.py'` from `/home/bwang/workspace/web_search` and confirm all legacy and new THSR regressions pass.
2. Run `python main.py` multiple times with representative queries, including `幫我查今天南港到嘉義最近的高鐵班次？`, `幫我查明天南港到嘉義大約下午3:00的高鐵班次？`, and `幫我查6/15南港到嘉義大約下午3:00的高鐵班次？`, and confirm the replies use the expected route and time semantics.
3. Add one focused validation for malformed LLM JSON or invalid station output, confirming the code falls back safely instead of returning hallucinated routes.
4. If the timetable PDF cannot reliably support the requested date, verify that the fallback message explicitly says the schedule source is static and points to the official THSR URL.

## Decisions

- Included scope: THSR queries should always attempt LLM-based structured extraction first, then pass through deterministic validation before lookup.
- Included scope: date semantics should expand beyond today to more complete natural language, starting with `今天`, `明天`, `後天`, explicit `MM/DD`, and common clock phrases such as `下午3:00`.
- Included scope: `大約下午3:00` means trains departing at or after `15:00`, not a symmetric time window and not earliest arrival.
- Excluded scope: seat availability, dynamic disruptions, fares by train, and authoritative holiday-special schedules, because the current PDF source is a static timetable rather than an official query API.
- Boundary: future-date replies are only as accurate as the currently published timetable PDF. When the source cannot guarantee day-specific exceptions, the assistant should say so explicitly.

## Further Considerations

1. Keep the LLM output contract small. A compact schema with a few enums is easier to validate than free-form JSON and reduces local-model drift.
2. Consider splitting intent extraction into a new helper module later if transport intent grows beyond THSR, but keep the first implementation local to `/home/bwang/workspace/web_search/transport_helpers.py` for minimal change surface.
3. If repeated malformed LLM output appears during validation, add telemetry or debug logging around the raw intent JSON before widening regex fallback behavior.
