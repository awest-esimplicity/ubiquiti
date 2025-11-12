import { ApiLockControllerAdapter } from "@/lib/adapters/apiLockController";
import { MockLockControllerAdapter } from "@/lib/adapters/mockLockController";
import { MockScheduleAdapter } from "@/lib/adapters/mockSchedule";
import { LockControllerService } from "@/lib/services/LockControllerService";
import { ScheduleService } from "@/lib/services/ScheduleService";

const env = import.meta.env as Record<string, string | undefined>;
const useMock = (env.PUBLIC_USE_MOCK_DATA ?? "true") !== "false";
const apiBaseUrl = env.PUBLIC_API_BASE_URL;

const lockAdapter = useMock
  ? new MockLockControllerAdapter()
  : new ApiLockControllerAdapter(apiBaseUrl);

// Schedules currently use the mock adapter in both modes until API endpoints are available.
const scheduleAdapter = new MockScheduleAdapter();

export const lockControllerService = new LockControllerService(lockAdapter);
export const scheduleService = new ScheduleService(scheduleAdapter);
