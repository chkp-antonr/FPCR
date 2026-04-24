# Package Selection Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the Domains page with a cascading selection flow for domains, policy packages, and sections with position selection.

**Architecture:**

- Backend: Add new FastAPI routes for packages and sections endpoints using cpaiops library
- Frontend: Transform existing Domains page from table-based to cascading AutoComplete selectors with section list and position radio group

**Tech Stack:** FastAPI, React, TypeScript, Ant Design, cpaiops

---

## Task 1: Add Backend Pydantic Models

**Files:**

- Modify: `src/fa/models.py`

**Step 1: Add the new model classes**

```python
# Add to src/fa/models.py after line 30

class PackageItem(BaseModel):
    """Single policy package item."""
    name: str
    uid: str
    access_layer: str


class SectionItem(BaseModel):
    """Single access section item with rule range."""
    name: str
    uid: str
    rulebase_range: tuple[int, int]  # (min_rule, max_rule)
    rule_count: int


class PackagesResponse(BaseModel):
    """Packages list response."""
    packages: list[PackageItem]


class SectionsResponse(BaseModel):
    """Sections list response."""
    sections: list[SectionItem]
    total_rules: int
```

**Step 2: Verify the file syntax**

Run: `python -m py_compile src/fa/models.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/fa/models.py
git commit -m "feat(api): add Pydantic models for packages and sections"
```

---

## Task 2: Create Packages Router

**Files:**

- Create: `src/fa/routes/packages.py`

**Step 1: Create the packages router file**

```python
"""Package and section endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request

from cpaiops import CPAIOPSClient

from ..models import (
    ErrorResponse,
    PackageItem,
    PackagesResponse,
    SectionItem,
    SectionsResponse,
)
from ..session import SessionData, SessionManager, session_manager

router = APIRouter(tags=["packages"])


async def get_session_data(request: Request):
    """Dependency to get current session."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


@router.get("/domains/{domain_uid}/packages", response_model=PackagesResponse)
async def list_packages(
    domain_uid: str, session: SessionData = Depends(get_session_data)
):
    """
    List all policy packages for a domain.

    Uses the authenticated user's credentials to connect to
    Check Point API and retrieve available packages.
    """
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    client = CPAIOPSClient(
        username=session.username,
        password=session.password,
        mgmt_ip=mgmt_ip,
    )

    try:
        async with client:
            server_names = client.get_mgmt_names()
            if not server_names:
                return PackagesResponse(packages=[])

            mgmt_name = server_names[0]
            result = await client.api_query(
                mgmt_name, "show-packages", {"domain": domain_uid}
            )

            if result.success:
                packages = [
                    PackageItem(
                        name=obj.get("name", ""),
                        uid=obj.get("uid", ""),
                        access_layer=obj.get("access-layer", ""),
                    )
                    for obj in (result.objects or [])
                ]
                return PackagesResponse(packages=packages)
            else:
                raise HTTPException(
                    status_code=500, detail=f"Check Point API error: {result.message}"
                )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Check Point: {str(e)}")


@router.get(
    "/domains/{domain_uid}/packages/{pkg_uid}/sections",
    response_model=SectionsResponse,
)
async def list_sections(
    domain_uid: str,
    pkg_uid: str,
    session: SessionData = Depends(get_session_data),
):
    """
    List all sections for a policy package with rule ranges.

    Returns sections in natural order with their rulebase ranges
    (min-max rule numbers within the section).
    """
    mgmt_ip = os.getenv("API_MGMT")
    if not mgmt_ip:
        raise HTTPException(status_code=500, detail="API_MGMT not configured")

    client = CPAIOPSClient(
        username=session.username,
        password=session.password,
        mgmt_ip=mgmt_ip,
    )

    try:
        async with client:
            server_names = client.get_mgmt_names()
            if not server_names:
                return SectionsResponse(sections=[], total_rules=0)

            mgmt_name = server_names[0]

            # First get the package to find its access layer
            pkg_result = await client.api_query(
                mgmt_name, "show-package", {"uid": pkg_uid, "domain": domain_uid}
            )

            if not pkg_result.success or not pkg_result.objects:
                raise HTTPException(
                    status_code=404, detail=f"Package not found: {pkg_result.message}"
                )

            package_data = pkg_result.objects[0]
            access_layer_name = package_data.get("access-layer", "")

            if not access_layer_name:
                return SectionsResponse(sections=[], total_rules=0)

            # Get the access rulebase
            layer_result = await client.api_query(
                mgmt_name,
                "show-access-rulebase",
                {"name": access_layer_name, "details-level": "full"},
            )

            if not layer_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Check Point API error: {layer_result.message}",
                )

            # Extract sections and calculate rule ranges
            sections = []
            current_rule = 1
            rulebase = layer_result.data.get("rulebase", [])

            for rule in rulebase:
                if rule.get("type") == "access-section":
                    section_name = rule.get("name", "")
                    section_uid = rule.get("uid", "")
                    section_rules = rule.get("rulebase", [])

                    section_min = current_rule
                    section_max = current_rule + len(section_rules) - 1
                    section_count = len(section_rules)

                    sections.append(
                        SectionItem(
                            name=section_name,
                            uid=section_uid,
                            rulebase_range=(section_min, section_max),
                            rule_count=section_count,
                        )
                    )

                    current_rule = section_max + 1

            total_rules = current_rule - 1

            return SectionsResponse(sections=sections, total_rules=total_rules)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Check Point: {str(e)}")
```

**Step 2: Verify the file syntax**

Run: `python -m py_compile src/fa/routes/packages.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/fa/routes/packages.py
git commit -m "feat(api): add packages and sections endpoints"
```

---

## Task 3: Register Packages Router

**Files:**

- Modify: `src/fa/routes/__init__.py`

**Step 1: Add packages router import and export**

```python
# Modify src/fa/routes/__init__.py
"""API route modules."""

from .auth import router as auth_router
from .domains import router as domains_router, DomainItem, DomainsResponse
from .health import router as health_router
from .packages import router as packages_router  # NEW

__all__ = [
    "auth_router",
    "domains_router",
    "health_router",
    "packages_router",  # NEW
    "DomainItem",
    "DomainsResponse",
]
```

**Step 2: Verify the file syntax**

Run: `python -m py_compile src/fa/routes/__init__.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/fa/routes/__init__.py
git commit -m "feat(api): register packages router"
```

---

## Task 4: Add Packages Router to App

**Files:**

- Modify: `src/fa/app.py`

**Step 1: Import and include packages_router**

```python
# Modify src/fa/app.py line 11
from .routes import auth_router, domains_router, health_router, packages_router

# Then add to router includes around line 43
app.include_router(packages_router, prefix="/api/v1")
```

**Step 2: Verify the file syntax**

Run: `python -m py_compile src/fa/app.py`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/fa/app.py
git commit -m "feat(api): include packages router in FastAPI app"
```

---

## Task 5: Add Frontend Types

**Files:**

- Modify: `webui/src/types/index.ts`

**Step 1: Add new TypeScript interfaces**

```typescript
// Add to webui/src/types/index.ts after line 25

export interface PackageItem {
  name: string;
  uid: string;
  access_layer: string;
}

export interface SectionItem {
  name: string;
  uid: string;
  rulebase_range: [number, number];  // [min, max]
  rule_count: number;
}

export interface SectionsResponse {
  sections: SectionItem[];
  total_rules: number;
}

export interface PackagesResponse {
  packages: PackageItem[];
}

export interface PositionChoice {
  type: 'top' | 'bottom' | 'custom';
  custom_number?: number;
}
```

**Step 2: Verify TypeScript compilation**

Run: `cd webui && npm run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add webui/src/types/index.ts
git commit -m "feat(types): add PackageItem, SectionItem, PositionChoice"
```

---

## Task 6: Add Packages API Endpoint Functions

**Files:**

- Modify: `webui/src/api/endpoints.ts`

**Step 1: Add packagesApi object**

```typescript
// Add to webui/src/api/endpoints.ts after line 25
import type {
  AuthResponse,
  DomainsResponse,
  LoginRequest,
  PackagesResponse,
  SectionsResponse,
  UserInfo
} from '../types';

// ... existing authApi, domainsApi ...

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
```

**Step 2: Verify TypeScript compilation**

Run: `cd webui && npm run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add webui/src/api/endpoints.ts
git commit -m "feat(api): add packagesApi list and getSections methods"
```

---

## Task 7: Rewrite Domains Page - Basic Layout

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

**Step 1: Replace entire file with new component structure**

```typescript
import { useState } from 'react';
import { Card, AutoComplete, Button, message, Spin } from 'antd';
import type { SelectProps } from 'antd/es/select';
import { domainsApi, packagesApi } from '../api/endpoints';
import type {
  DomainItem,
  PackageItem,
  SectionItem,
  PositionChoice
} from '../types';

export default function Domains() {
  // Domain state
  const [domains, setDomains] = useState<DomainItem[]>([]);
  const [domainOptions, setDomainOptions] = useState<SelectProps['options']>([]);
  const [selectedDomain, setSelectedDomain] = useState<DomainItem | null>(null);
  const [domainSearch, setDomainSearch] = useState('');

  // Package state
  const [packages, setPackages] = useState<PackageItem[]>([]);
  const [packageOptions, setPackageOptions] = useState<SelectProps['options']>([]);
  const [selectedPackage, setSelectedPackage] = useState<PackageItem | null>(null);
  const [packageSearch, setPackageSearch] = useState('');
  const [packagesLoading, setPackagesLoading] = useState(false);

  // Section state
  const [sections, setSections] = useState<SectionItem[]>([]);
  const [selectedSection, setSelectedSection] = useState<SectionItem | null>(null);
  const [sectionsLoading, setSectionsLoading] = useState(false);

  // Position state
  const [positionType, setPositionType] = useState<'top' | 'bottom' | 'custom' | null>(null);
  const [customNumber, setCustomNumber] = useState<number | null>(null);

  // General loading
  const [initialLoading, setInitialLoading] = useState(true);

  const fetchDomains = async () => {
    try {
      const response = await domainsApi.list();
      setDomains(response.domains);
      const options = response.domains.map(d => ({ value: d.uid, label: d.name }));
      setDomainOptions(options);
    } catch {
      message.error('Failed to load domains');
    } finally {
      setInitialLoading(false);
    }
  };

  const fetchPackages = async (domainUid: string) => {
    setPackagesLoading(true);
    try {
      const response = await packagesApi.list(domainUid);
      setPackages(response.packages);
      const options = response.packages.map(p => ({ value: p.uid, label: p.name }));
      setPackageOptions(options);
    } catch {
      message.error('Failed to load packages');
    } finally {
      setPackagesLoading(false);
    }
  };

  const fetchSections = async (domainUid: string, pkgUid: string) => {
    setSectionsLoading(true);
    try {
      const response = await packagesApi.getSections(domainUid, pkgUid);
      setSections(response.sections);
    } catch {
      message.error('Failed to load sections');
    } finally {
      setSectionsLoading(false);
    }
  };

  // Initial load
  useState(() => {
    fetchDomains();
  });

  return (
    <div style={{ padding: 24 }}>
      <Card title="Domains">
        <Spin spinning={initialLoading}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8 }}>Domain:</label>
            <AutoComplete
              style={{ width: '100%' }}
              options={domainOptions}
              value={domainSearch}
              onChange={setDomainSearch}
              onSelect={(value) => {
                const domain = domains.find(d => d.uid === value);
                if (domain) {
                  setSelectedDomain(domain);
                  setSelectedPackage(null);
                  setSections([]);
                  setSelectedSection(null);
                  setPositionType(null);
                  setCustomNumber(null);
                  fetchPackages(domain.uid);
                }
              }}
              placeholder="Search domain..."
              filterOption={(inputValue, option) =>
                option?.label?.toString().toLowerCase().includes(inputValue.toLowerCase())
              }
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8 }}>Package:</label>
            <AutoComplete
              style={{ width: '100%' }}
              options={packageOptions}
              value={packageSearch}
              onChange={setPackageSearch}
              disabled={!selectedDomain}
              loading={packagesLoading}
              onSelect={(value) => {
                const pkg = packages.find(p => p.uid === value);
                if (pkg && selectedDomain) {
                  setSelectedPackage(pkg);
                  setSelectedSection(null);
                  setPositionType(null);
                  setCustomNumber(null);
                  fetchSections(selectedDomain.uid, pkg.uid);
                }
              }}
              placeholder="Search package..."
              filterOption={(inputValue, option) =>
                option?.label?.toString().toLowerCase().includes(inputValue.toLowerCase())
              }
            />
          </div>

          {sections.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 8 }}>Sections:</label>
              <Spin spinning={sectionsLoading}>
                {sections.map((section) => (
                  <div
                    key={section.uid}
                    onClick={() => setSelectedSection(section)}
                    style={{
                      padding: '8px 12px',
                      border: '1px solid #d9d9d9',
                      borderRadius: 4,
                      marginBottom: 8,
                      cursor: 'pointer',
                      backgroundColor: selectedSection?.uid === section.uid ? '#e6f7ff' : 'white',
                    }}
                  >
                    {section.rulebase_range[0]}-{section.rulebase_range[1]} {section.name}
                  </div>
                ))}
              </Spin>
            </div>
          )}
        </Spin>
      </Card>
    </div>
  );
}
```

**Step 2: Verify TypeScript compilation**

Run: `cd webui && npm run type-check`
Expected: No errors (might have useState warning, we'll fix)

**Step 3: Fix useState hook call**

The useState in the wrong place - should be useEffect. Replace the initial load part:

```typescript
// Replace the useState(() => { fetchDomains(); }); at bottom with:

import { useEffect, useState } from 'react';

// ... keep all state declarations ...

useEffect(() => {
  fetchDomains();
}, []);
```

**Step 4: Verify TypeScript compilation**

Run: `cd webui && npm run type-check`
Expected: No errors

**Step 5: Commit**

```bash
git add webui/src/pages/Domains.tsx
git commit -m "feat(ui): add domain and package selectors to Domains page"
```

---

## Task 8: Add Position Selector and Submit Button

**Files:**

- Modify: `webui/src/pages/Domains.tsx`

**Step 1: Add imports and position selector UI**

```typescript
// Add Radio and InputNumber to imports (line 3)
import { Card, AutoComplete, Button, message, Spin, Radio, InputNumber } from 'antd';

// ... after the sections section, add:

{selectedSection && (
  <div style={{ marginBottom: 16 }}>
    <label style={{ display: 'block', marginBottom: 8 }}>Position:</label>
    <Radio.Group
      value={positionType}
      onChange={(e) => {
        setPositionType(e.target.value);
        setCustomNumber(null);
      }}
    >
      <Radio value="top">Top</Radio>
      <Radio value="bottom">Bottom</Radio>
      <Radio value="custom">
        Custom:{' '}
        {positionType === 'custom' && (
          <InputNumber
            min={selectedSection.rulebase_range[0]}
            max={selectedSection.rulebase_range[1]}
            value={customNumber}
            onChange={(value) => setCustomNumber(value)}
            style={{ width: 80, marginLeft: 8 }}
          />
        )}
      </Radio>
    </Radio.Group>
    {positionType === 'custom' &&
      (customNumber === null ||
        customNumber < selectedSection.rulebase_range[0] ||
        customNumber > selectedSection.rulebase_range[1]) && (
        <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>
          Must be between {selectedSection.rulebase_range[0]} and {selectedSection.rulebase_range[1]}
        </div>
      )}
  </div>
)}

{selectedSection && positionType && (
  <Button
    type="primary"
    disabled={
      !positionType ||
      (positionType === 'custom' &&
        (customNumber === null ||
          customNumber < selectedSection.rulebase_range[0] ||
          customNumber > selectedSection.rulebase_range[1]))
    }
    onClick={() => {
      const payload: PositionChoice = {
        type: positionType,
        custom_number: positionType === 'custom' ? customNumber ?? 0 : undefined,
      };
      console.log('Submit payload:', {
        domain: selectedDomain?.uid,
        package: selectedPackage?.uid,
        section: selectedSection?.uid,
        position: payload,
      });
      message.success('Selection saved (Phase 1 - no backend action yet)');
    }}
  >
    Submit
  </Button>
)}
```

**Step 2: Verify TypeScript compilation**

Run: `cd webui && npm run type-check`
Expected: No errors

**Step 3: Commit**

```bash
git add webui/src/pages/Domains.tsx
git commit -m "feat(ui): add position selector and submit button"
```

---

## Task 9: Backend Manual Testing

**Files:**

- (no files modified - manual testing)

**Step 1: Start the backend server**

Run: `uv run uvicorn src.fa.app:app --reload --host 0.0.0.0 --port 8000`
Expected: Server starts, shows "FPCR WebUI starting..."

**Step 2: Test health endpoint**

Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok","service":"fpcr-webui"}`

**Step 3: Login to get session cookie**

Run: `curl -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"YOUR_USER","password":"YOUR_PASS"}'`
Expected: `{"message":"Logged in successfully","username":"YOUR_USER"}`

**Step 4: Test domains endpoint**

Run: `curl -b cookies.txt http://localhost:8000/api/v1/domains`
Expected: JSON with domains list

**Step 5: Test packages endpoint**

Run: `curl -b cookies.txt http://localhost:8000/api/v1/domains/{DOMAIN_UID}/packages`
Expected: JSON with packages list

**Step 6: Test sections endpoint**

Run: `curl -b cookies.txt http://localhost:8000/api/v1/domains/{DOMAIN_UID}/packages/{PACKAGE_UID}/sections`
Expected: JSON with sections and rulebase_range tuples

**Step 7: Check API documentation**

Open browser: `http://localhost:8000/api/v1/docs`
Expected: Swagger UI showing all endpoints including new packages routes

---

## Task 10: Frontend Build Verification

**Files:**

- (no files modified - build verification)

**Step 1: Install dependencies**

Run: `cd webui && npm install`
Expected: Dependencies installed successfully

**Step 2: Type check**

Run: `cd webui && npm run type-check`
Expected: No TypeScript errors

**Step 3: Build**

Run: `cd webui && npm run build`
Expected: Build succeeds, dist/ directory created

**Step 4: Start backend with built frontend**

Run: `uv run uvicorn src.fa.app:app --reload --host 0.0.0.0 --port 8000`
Expected: Server serves React app from /

**Step 5: Open browser**

Open: `http://localhost:8000`
Expected: Login page loads

**Step 6: Login and navigate**

1. Login with valid credentials
2. Navigate to Domains page
3. Type in domain search → filtered results
4. Select domain → packages loads
5. Type in package search → filtered results
6. Select package → sections list appears
7. Click section → position selector enables
8. Select Custom → number input appears
9. Enter invalid number → validation error shows
10. Enter valid number → Submit button enables
11. Click Submit → console logs payload, success message shows

---

## Task 11: Update Navigation and Documentation

**Files:**

- Modify: `README.md`

**Step 1: Update README with new feature**

```markdown
Add to README.md in the WebUI section:

## Package Selection Flow

The Domains page includes a cascading selection flow for exploring policy packages:

1. **Domain Selection** - Search and select a domain
2. **Package Selection** - Search and select a policy package
3. **Section View** - View all sections with their rule ranges
4. **Position Selection** - Choose Top, Bottom, or Custom rule number

This provides the foundation for rule insertion operations in Phase 2.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document package selection flow in README"
```

---

## Summary

This implementation plan creates a complete Phase 1 package selection flow:

**Backend (6 tasks):**

- Add Pydantic models for PackageItem, SectionItem
- Create packages router with list_packages and list_sections endpoints
- Integrate with cpaiops for Check Point API calls
- Register routes in FastAPI app

**Frontend (4 tasks):**

- Add TypeScript types for packages and sections
- Add API functions for packages and sections endpoints
- Rewrite Domains page with cascading AutoComplete selectors
- Add position selector with validation and submit button

**Testing (2 tasks):**

- Backend endpoint testing via curl and Swagger docs
- Frontend build verification and manual UI testing

**Total:** 12 tasks, ~12-18 commits (following TDD with frequent commits)
