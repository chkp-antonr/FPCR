import apiClient from './client';
import type {
  AuthResponse,
  BatchRulesResponse,
  CacheStatusResponse,
  CreateRuleRequest,
  Domains2BatchRequest,
  DomainsResponse,
  LoginRequest,
  PackagesResponse,
  PublishResponse,
  RITMCreateRequest,
  RITMItem,
  RITMListResponse,
  RITMUpdateRequest,
  RITMWithPolicies,
  SectionsResponse,
  TopologyResponse,
  UserInfo,
  PolicyItem,
  PlanYamlResponse,
  ApplyResponse,
  VerifyResponse,
  TryVerifyResponse,
  EvidenceResponse,
} from '../types';

export const authApi = {
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/api/v1/auth/login', credentials);
    return response.data;
  },

  logout: async (): Promise<AuthResponse> => {
    const response = await apiClient.post<AuthResponse>('/api/v1/auth/logout');
    return response.data;
  },

  getMe: async (): Promise<UserInfo> => {
    const response = await apiClient.get<UserInfo>('/api/v1/auth/me');
    return response.data;
  },
};

export const domainsApi = {
  list: async (): Promise<DomainsResponse> => {
    const response = await apiClient.get<DomainsResponse>('/api/v1/domains');
    return response.data;
  },
};

export const packagesApi = {
  list: async (domainUid: string): Promise<PackagesResponse> => {
    const response = await apiClient.get<PackagesResponse>(
      `/api/v1/domains/${domainUid}/packages`
    );
    return response.data;
  },

  getSections: async (
    domainUid: string,
    pkgUid: string
  ): Promise<SectionsResponse> => {
    const response = await apiClient.get<SectionsResponse>(
      `/api/v1/domains/${domainUid}/packages/${pkgUid}/sections`
    );
    return response.data;
  },
};

export const rulesApi = {
  createBatch: async (rules: CreateRuleRequest[]): Promise<BatchRulesResponse> => {
    const response = await apiClient.post<BatchRulesResponse>(
      '/api/v1/domains/rules/batch',
      rules
    );
    return response.data;
  },
};

// === Domains_2 APIs ===

export const topologyApi = {
  getTopology: async (): Promise<TopologyResponse> => {
    const response = await apiClient.get<TopologyResponse>('/api/v1/domains/topology');
    return response.data;
  },
};

export const rules2Api = {
  createBatch: async (data: Domains2BatchRequest): Promise<BatchRulesResponse> => {
    const response = await apiClient.post<BatchRulesResponse>(
      '/api/v1/domains2/rules/batch',
      data
    );
    return response.data;
  },
};

export const cacheApi = {
  getStatus: async (): Promise<CacheStatusResponse> => {
    const response = await apiClient.get<CacheStatusResponse>('/api/v1/cache/status');
    return response.data;
  },

  refresh: async (): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>('/api/v1/cache/refresh');
    return response.data;
  },
};

// === RITM APIs ===

export const ritmApi = {
  create: async (request: RITMCreateRequest): Promise<RITMItem> => {
    const response = await apiClient.post<RITMItem>('/api/v1/ritm', request);
    return response.data;
  },

  list: async (params?: { status?: number; username?: string }): Promise<RITMListResponse> => {
    const response = await apiClient.get<RITMListResponse>('/api/v1/ritm', { params });
    return response.data;
  },

  get: async (ritmNumber: string): Promise<RITMWithPolicies> => {
    const response = await apiClient.get<RITMWithPolicies>(`/api/v1/ritm/${ritmNumber}`);
    return response.data;
  },

  update: async (ritmNumber: string, request: RITMUpdateRequest): Promise<RITMItem> => {
    const response = await apiClient.put<RITMItem>(`/api/v1/ritm/${ritmNumber}`, request);
    return response.data;
  },

  savePolicy: async (ritmNumber: string, policies: PolicyItem[]): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(
      `/api/v1/ritm/${ritmNumber}/policy`,
      policies
    );
    return response.data;
  },

  savePools: async (ritmNumber: string, pools: { source_ips: string[]; dest_ips: string[]; services: string[] }): Promise<{ message: string }> => {
    const response = await apiClient.post<{ message: string }>(
      `/api/v1/ritm/${ritmNumber}/pools`,
      pools
    );
    return response.data;
  },

  publish: async (ritmNumber: string): Promise<PublishResponse> => {
    const response = await apiClient.post<PublishResponse>(`/api/v1/ritm/${ritmNumber}/publish`);
    return response.data;
  },

  acquireLock: async (ritmNumber: string): Promise<RITMItem> => {
    const response = await apiClient.post<RITMItem>(`/api/v1/ritm/${ritmNumber}/lock`);
    return response.data;
  },

  releaseLock: async (ritmNumber: string): Promise<RITMItem> => {
    const response = await apiClient.post<RITMItem>(`/api/v1/ritm/${ritmNumber}/unlock`);
    return response.data;
  },

  // RITM Flow APIs
  matchObjects: async (ritmNumber: string, data: { source_ips: string[]; dest_ips: string[]; services: string[]; domain_uid: string }): Promise<any> => {
    const response = await apiClient.post<any>(`/api/v1/ritm/${ritmNumber}/match-objects`, data);
    return response.data;
  },

  verifyPolicy: async (ritmNumber: string, domainUid: string, packageUid: string): Promise<any> => {
    const response = await apiClient.post<any>(
      `/api/v1/ritm/${ritmNumber}/verify-policy?domain_uid=${encodeURIComponent(domainUid)}&package_uid=${encodeURIComponent(packageUid)}`
    );
    return response.data;
  },

  generateEvidence: async (ritmNumber: string): Promise<any> => {
    const response = await apiClient.post<any>(`/api/v1/ritm/${ritmNumber}/generate-evidence`);
    return response.data;
  },

  generatePlanYaml: async (ritmNumber: string): Promise<PlanYamlResponse> => {
    const response = await apiClient.post<PlanYamlResponse>(`/api/v1/ritm/${ritmNumber}/plan-yaml`);
    return response.data;
  },

  applyRitm: async (ritmNumber: string): Promise<ApplyResponse> => {
    const response = await apiClient.post<ApplyResponse>(`/api/v1/ritm/${ritmNumber}/apply`);
    return response.data;
  },

  verifyRitm: async (ritmNumber: string): Promise<VerifyResponse> => {
    const response = await apiClient.post<VerifyResponse>(`/api/v1/ritm/${ritmNumber}/verify`);
    return response.data;
  },

  tryVerifyRitm: async (ritmNumber: string): Promise<TryVerifyResponse> => {
    const response = await apiClient.post<TryVerifyResponse>(
      `/api/v1/ritm/${ritmNumber}/try-verify`
    );
    return response.data;
  },

  recreateEvidence: async (ritmNumber: string): Promise<EvidenceResponse> => {
    const response = await apiClient.post<EvidenceResponse>(
      `/api/v1/ritm/${ritmNumber}/recreate-evidence`
    );
    return response.data;
  },

  exportErrors: async (ritmNumber: string): Promise<string> => {
    const response = await apiClient.get<string>(`/api/v1/ritm/${ritmNumber}/export-errors`);
    return response.data;
  },

  getSessionEvidenceHtml: async (ritmNumber: string, evidence: number = 1): Promise<string> => {
    const response = await apiClient.get<string>(`/api/v1/ritm/${ritmNumber}/session-html?evidence=${evidence}`, {
      responseType: 'text',
      headers: {
        Accept: 'text/html',
      },
    });
    return response.data;
  },
};
