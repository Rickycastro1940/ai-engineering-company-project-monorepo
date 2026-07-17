import { mountBackoffice } from "./app";
import { initTelemetry } from "./telemetry/instrumentation";

initTelemetry("ops_med_001");
mountBackoffice(document.getElementById("app")!);
