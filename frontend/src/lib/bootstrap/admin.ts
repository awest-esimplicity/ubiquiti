import { ApiAdminAdapter } from "@/lib/adapters/apiAdmin";
import { MockAdminAdapter } from "@/lib/adapters/mockAdmin";
import { AdminService } from "@/lib/services/AdminService";

const env = import.meta.env as Record<string, string | undefined>;
const useMock = (env.PUBLIC_USE_MOCK_DATA ?? "true") !== "false";
const apiBaseUrl = env.PUBLIC_API_BASE_URL;

const adminAdapter = useMock ? new MockAdminAdapter() : new ApiAdminAdapter(apiBaseUrl);

export const adminService = new AdminService(adminAdapter);
