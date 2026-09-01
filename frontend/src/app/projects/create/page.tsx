"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import {
  countryOptions,
  districtOptions,
  firstDistrict,
  firstProvince,
  optionLabel,
  provinceOptions,
} from "@/lib/profile-options";
import {
  researchDirectionLabel,
  researchTopicDirection,
  researchTopicLabel,
  researchTopicsByDirection,
} from "@/lib/research-topics";
import { useAuth } from "@/lib/auth";

type FieldKind = "text" | "number" | "textarea" | "date" | "select" | "array";

type FormField = {
  key: string;
  label: string;
  kind?: FieldKind;
  description?: string;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  fields?: FormField[];
  itemLabel?: string;
  span?: "full";
};

type FormSection = {
  title: string;
  description?: string;
  fields: FormField[];
};

type ProjectFormState = {
  title: string;
  summary: string;
  description: string;
  status: string;
  research_topics: string[];
  custom_research_topics: string;
  keywords: string;
  country: string;
  province: string;
  district: string;
  details: Record<string, unknown>;
};

const statusOptions = [
  { value: "draft", label: "Draft" },
  { value: "proposed", label: "Proposed" },
  { value: "ongoing", label: "Ongoing" },
  { value: "completed", label: "Completed" },
  { value: "paused", label: "Paused" },
];

const proficiencyOptions = [
  { value: "beginner", label: "Cơ bản" },
  { value: "intermediate", label: "Trung bình" },
  { value: "advanced", label: "Thành thạo" },
  { value: "expert", label: "Chuyên gia" },
];

const outputTypeOptions = [
  { value: "Algorithm", label: "Algorithm" },
  { value: "Platform", label: "Platform" },
  { value: "Paper", label: "Bài báo" },
  { value: "Patent", label: "Bằng sáng chế" },
  { value: "Product", label: "Sản phẩm" },
  { value: "Dataset", label: "Dataset" },
];

const privacyOptions = [
  { value: "Public", label: "Public" },
  { value: "Restricted", label: "Restricted" },
  { value: "Private", label: "Private" },
];

const projectSections: FormSection[] = [
  {
    title: "Requirements and timeline",
    description: "Thông tin này ảnh hưởng trực tiếp đến matching với expert, enterprise và funder.",
    fields: [
      {
        key: "requirements_and_timeline.required_skills",
        label: "Kỹ năng bắt buộc",
        kind: "array",
        itemLabel: "Kỹ năng",
        description: "Danh sách kỹ năng/phương pháp mà dự án cần. Nên dùng tên rõ ràng để KG ánh xạ tốt hơn.",
        fields: [
          { key: "name", label: "Tên kỹ năng", placeholder: "Ví dụ: Python, PyTorch, Computer Vision" },
          { key: "category", label: "Nhóm", placeholder: "Programming, Framework, Method, Domain" },
          { key: "proficiency_level", label: "Mức độ", kind: "select", options: proficiencyOptions },
        ],
      },
      {
        key: "requirements_and_timeline.technology_readiness_level",
        label: "Technology readiness level",
        kind: "number",
        description: "TRL 1-9 của dự án hiện tại.",
        placeholder: "4",
      },
      { key: "requirements_and_timeline.budget.amount", label: "Ngân sách", kind: "number", placeholder: "100000" },
      {
        key: "requirements_and_timeline.budget.currency",
        label: "Tiền tệ",
        kind: "select",
        options: [
          { value: "USD", label: "USD" },
          { value: "VND", label: "VND" },
          { value: "EUR", label: "EUR" },
        ],
      },
      {
        key: "requirements_and_timeline.budget.budget_type",
        label: "Loại ngân sách",
        kind: "select",
        options: [
          { value: "Grant", label: "Grant" },
          { value: "Co-funding Grant", label: "Co-funding Grant" },
          { value: "Internal", label: "Nội bộ" },
          { value: "Investment", label: "Đầu tư" },
        ],
      },
      {
        key: "requirements_and_timeline.deliverables",
        label: "Sản phẩm bàn giao",
        kind: "array",
        itemLabel: "Deliverable",
        fields: [{ key: "value", label: "Nội dung", placeholder: "Source code, report, patent, API..." }],
      },
      { key: "requirements_and_timeline.timeline.start_date", label: "Ngày bắt đầu", kind: "date" },
      { key: "requirements_and_timeline.timeline.end_date", label: "Ngày kết thúc", kind: "date" },
      {
        key: "requirements_and_timeline.collaboration_needs.expert_roles_needed",
        label: "Vai trò expert cần tìm",
        kind: "array",
        itemLabel: "Vai trò",
        fields: [{ key: "value", label: "Vai trò", placeholder: "Clinical Data Annotator, Industrial Data Engineer..." }],
      },
      {
        key: "requirements_and_timeline.collaboration_needs.enterprise_partner_type",
        label: "Loại đối tác doanh nghiệp",
        placeholder: "Hospital or Clinic, Manufacturing Enterprise...",
      },
      {
        key: "requirements_and_timeline.collaboration_needs.expected_contribution",
        label: "Đóng góp kỳ vọng",
        kind: "textarea",
        span: "full",
        placeholder: "Provide dataset, pilot site, equipment, domain experts...",
      },
    ],
  },
  {
    title: "R&D profile",
    description: "Mô tả đầu ra, dataset, tiến độ TRL, khoảng cách công nghệ và tác động.",
    fields: [
      {
        key: "rd_profile.outputs",
        label: "Outputs",
        kind: "array",
        itemLabel: "Output",
        fields: [
          { key: "type", label: "Loại", kind: "select", options: outputTypeOptions },
          { key: "title", label: "Tiêu đề" },
          { key: "year", label: "Năm", kind: "number" },
          { key: "id", label: "ID sản phẩm/dataset/paper" },
        ],
      },
      {
        key: "rd_profile.required_dataset_ids",
        label: "Dataset cần thiết",
        kind: "array",
        itemLabel: "Dataset",
        fields: [{ key: "value", label: "Dataset ID", placeholder: "ds_001" }],
      },
      {
        key: "rd_profile.trl_progression",
        label: "Tiến độ TRL",
        kind: "array",
        itemLabel: "TRL",
        fields: [
          { key: "year", label: "Năm", kind: "number" },
          { key: "trl_level", label: "TRL level", kind: "number" },
        ],
      },
      { key: "rd_profile.technology_gap.current_trl", label: "TRL hiện tại", kind: "number" },
      { key: "rd_profile.technology_gap.target_trl", label: "TRL mục tiêu", kind: "number" },
      {
        key: "rd_profile.technology_gap.gap_description",
        label: "Mô tả khoảng cách công nghệ",
        kind: "textarea",
        span: "full",
      },
      { key: "rd_profile.impact_and_sustainability.impact_metrics.papers_count", label: "Số bài báo", kind: "number" },
      { key: "rd_profile.impact_and_sustainability.impact_metrics.patents_count", label: "Số bằng sáng chế", kind: "number" },
      {
        key: "rd_profile.impact_and_sustainability.impact_metrics.commercialization_revenue",
        label: "Doanh thu thương mại hóa",
        kind: "number",
      },
      {
        key: "rd_profile.impact_and_sustainability.sustainability_metrics",
        label: "Chỉ số tác động/bền vững",
        kind: "textarea",
        span: "full",
      },
    ],
  },
  {
    title: "Relations",
    description: "Các liên kết nghiệp vụ giúp Neo4j tạo đường dẫn giải thích rõ hơn.",
    fields: [
      {
        key: "relations.participants",
        label: "Expert tham gia",
        kind: "array",
        itemLabel: "Expert",
        fields: [
          { key: "expert_id", label: "Expert ID", placeholder: "exp_001" },
          { key: "role", label: "Vai trò", placeholder: "PI, Co-PI, Advisor" },
          { key: "period", label: "Thời gian", placeholder: "2024-2026" },
        ],
      },
      {
        key: "relations.enterprise_partners",
        label: "Đối tác doanh nghiệp",
        kind: "array",
        itemLabel: "Enterprise",
        fields: [
          { key: "enterprise_id", label: "Enterprise ID", placeholder: "ent_001" },
          { key: "type", label: "Loại hợp tác", placeholder: "Industry Partner" },
        ],
      },
      {
        key: "relations.funders",
        label: "Funder",
        kind: "array",
        itemLabel: "Funder",
        fields: [
          { key: "funder_id", label: "Funder ID", placeholder: "fnd_001" },
          { key: "grant_period", label: "Grant period", placeholder: "2024-2026" },
          { key: "grant_amount", label: "Grant amount", kind: "number" },
        ],
      },
      {
        key: "relations.target_industries",
        label: "Ngành mục tiêu",
        kind: "array",
        itemLabel: "Industry",
        fields: [
          { key: "code", label: "Mã ngành", placeholder: "HEAL, MFG, EDU" },
          { key: "name", label: "Tên ngành", placeholder: "Healthcare Technology" },
        ],
      },
      {
        key: "relations.related_projects",
        label: "Dự án liên quan",
        kind: "array",
        itemLabel: "Project",
        fields: [{ key: "value", label: "Project ID", placeholder: "prj_001" }],
      },
    ],
  },
  {
    title: "Follow-up opportunities",
    description: "Thông tin mở rộng cho giai đoạn sau, spin-off và scale-up.",
    fields: [
      { key: "follow_up_opportunities.next_phase_project_id", label: "Next phase project ID" },
      {
        key: "follow_up_opportunities.spin_off_potential",
        label: "Tiềm năng spin-off",
        kind: "textarea",
        span: "full",
      },
      { key: "follow_up_opportunities.scale_up_plan", label: "Kế hoạch scale-up", kind: "textarea", span: "full" },
    ],
  },
  {
    title: "Governance",
    description: "Quyền riêng tư và độ mới của dữ liệu. Các trường này giúp quản trị viên kiểm soát chất lượng dữ liệu.",
    fields: [
      { key: "governance.privacy.privacy_level", label: "Privacy level", kind: "select", options: privacyOptions },
      { key: "governance.privacy.field_privacy.requirements_and_timeline.budget", label: "Quyền riêng tư của ngân sách", kind: "select", options: privacyOptions },
      {
        key: "governance.privacy.consent.status",
        label: "Consent status",
        kind: "select",
        options: [
          { value: "granted", label: "Granted" },
          { value: "pending", label: "Pending" },
          { value: "revoked", label: "Revoked" },
        ],
      },
      { key: "governance.privacy.consent.date", label: "Consent date", kind: "date" },
      { key: "governance.temporal_freshness.last_update", label: "Ngày cập nhật gần nhất", kind: "date" },
      { key: "governance.temporal_freshness.update_source", label: "Nguồn cập nhật", placeholder: "User_Profile, Project_Lead..." },
      { key: "governance.temporal_freshness.freshness_score", label: "Freshness score", kind: "number" },
    ],
  },
];

function getNestedValue(source: Record<string, unknown> | undefined, path: string) {
  return path.split(".").reduce<unknown>((current, key) => {
    if (!current || typeof current !== "object") return undefined;
    return (current as Record<string, unknown>)[key];
  }, source);
}

function setNestedValue(source: Record<string, unknown> | undefined, path: string, value: unknown) {
  const next = structuredClone(source ?? {}) as Record<string, unknown>;
  const keys = path.split(".");
  let current = next;
  keys.slice(0, -1).forEach((key) => {
    if (!current[key] || typeof current[key] !== "object" || Array.isArray(current[key])) current[key] = {};
    current = current[key] as Record<string, unknown>;
  });
  current[keys[keys.length - 1]] = value;
  return next;
}

function toNumberOrNull(value: unknown) {
  if (value === "" || value === undefined || value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function removeEmpty(value: unknown): unknown {
  if (Array.isArray(value)) {
    const cleaned = value
      .map((item) => {
        if (item && typeof item === "object" && !Array.isArray(item) && "value" in item) {
          return removeEmpty((item as Record<string, unknown>).value);
        }
        return removeEmpty(item);
      })
      .filter((item) => item !== "" && item !== null && item !== undefined);
    return cleaned.length ? cleaned : undefined;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => [key, removeEmpty(item)] as const)
      .filter(([, item]) => item !== "" && item !== null && item !== undefined);
    return entries.length ? Object.fromEntries(entries) : undefined;
  }
  return value;
}

function emptyArrayItem(field: FormField) {
  return Object.fromEntries((field.fields ?? []).map((child) => [child.key, ""]));
}

export default function CreateProjectPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState<ProjectFormState>({
    title: "",
    summary: "",
    description: "",
    status: "draft",
    research_topics: [],
    custom_research_topics: "",
    keywords: "",
    country: "VN",
    province: firstProvince("VN"),
    district: "",
    details: {
      governance: {
        privacy: {
          privacy_level: "Public",
          consent: { status: "granted" },
        },
        temporal_freshness: {
          update_source: "User_Profile",
        },
      },
    },
  });

  useEffect(() => {
    if (!isLoading && !user) router.push("/auth/login");
  }, [isLoading, router, user]);

  useEffect(() => {
    setForm((current) => {
      if (current.district) return current;
      return { ...current, district: firstDistrict(current.country, current.province) };
    });
  }, []);

  const countries = countryOptions();
  const provinces = provinceOptions(form.country);
  const districts = districtOptions(form.country, form.province);
  const topicGroups = researchTopicsByDirection();
  const selectedDirections = useMemo(
    () => Array.from(new Set(form.research_topics.map((topic) => researchTopicDirection(topic)).filter(Boolean) as string[])),
    [form.research_topics],
  );

  function updateForm(patch: Partial<ProjectFormState>) {
    setForm((current) => ({ ...current, ...patch }));
    setError("");
  }

  function updateDetails(path: string, value: unknown) {
    setForm((current) => ({ ...current, details: setNestedValue(current.details, path, value) }));
    setError("");
  }

  function addArrayItem(path: string, field: FormField) {
    const current = getNestedValue(form.details, path);
    const items = Array.isArray(current) ? current : [];
    updateDetails(path, [...items, emptyArrayItem(field)]);
  }

  function removeArrayItem(path: string, index: number) {
    const current = getNestedValue(form.details, path);
    const items = Array.isArray(current) ? current : [];
    updateDetails(
      path,
      items.filter((_, itemIndex) => itemIndex !== index),
    );
  }

  function updateArrayItem(path: string, index: number, key: string, value: unknown) {
    const current = getNestedValue(form.details, path);
    const items = Array.isArray(current) ? [...current] : [];
    const item = typeof items[index] === "object" && items[index] !== null ? { ...(items[index] as Record<string, unknown>) } : {};
    item[key] = value;
    items[index] = item;
    updateDetails(path, items);
  }

  function toggleTopic(topic: string) {
    const exists = form.research_topics.includes(topic);
    updateForm({
      research_topics: exists ? form.research_topics.filter((item) => item !== topic) : [...form.research_topics, topic],
    });
  }

  function renderScalarField(field: FormField, value: unknown, onChange: (value: string) => void) {
    const textValue = value === undefined || value === null ? "" : String(value);
    if (field.kind === "textarea") {
      return <Textarea value={textValue} rows={4} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} />;
    }
    if (field.kind === "select") {
      return (
        <Select value={textValue} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder={`Chọn ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    return (
      <Input
        type={field.kind === "number" ? "number" : field.kind === "date" ? "date" : "text"}
        value={textValue}
        placeholder={field.placeholder}
        min={field.key.toLowerCase().includes("trl") ? 1 : undefined}
        max={field.key.toLowerCase().includes("trl") ? 9 : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  function renderField(field: FormField) {
    if (field.kind === "array") {
      const value = getNestedValue(form.details, field.key);
      const items = Array.isArray(value) ? value : [];
      return (
        <div key={field.key} className="space-y-3 md:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Label>{field.label}</Label>
              {field.description ? <p className="mt-1 text-xs text-muted-foreground">{field.description}</p> : null}
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => addArrayItem(field.key, field)}>
              <Plus className="mr-2 h-4 w-4" />
              Thêm mục
            </Button>
          </div>
          <div className="space-y-3">
            {items.length === 0 ? (
              <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
                Chưa có dữ liệu. Bấm "Thêm mục" để nhập {field.label.toLowerCase()}.
              </div>
            ) : (
              items.map((item, index) => {
                const itemRecord = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
                return (
                  <div key={`${field.key}-${index}`} className="rounded-2xl border bg-slate-50/80 p-4">
                    <div className="mb-4 flex items-center justify-between gap-2">
                      <div className="font-semibold">
                        {field.itemLabel ?? field.label} #{index + 1}
                      </div>
                      <Button type="button" variant="ghost" size="icon" onClick={() => removeArrayItem(field.key, index)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      {(field.fields ?? []).map((child) => (
                        <div key={child.key} className={child.span === "full" || child.kind === "textarea" ? "space-y-2 md:col-span-2" : "space-y-2"}>
                          <Label>{child.label}</Label>
                          {child.description ? <p className="text-xs text-muted-foreground">{child.description}</p> : null}
                          {renderScalarField(child, itemRecord[child.key], (nextValue) => updateArrayItem(field.key, index, child.key, nextValue))}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      );
    }

    const value = getNestedValue(form.details, field.key);
    return (
      <div key={field.key} className={field.span === "full" || field.kind === "textarea" ? "space-y-2 md:col-span-2" : "space-y-2"}>
        <Label>{field.label}</Label>
        {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
        {renderScalarField(field, value, (nextValue) => updateDetails(field.key, nextValue))}
      </div>
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const cleanDetails = (removeEmpty(form.details) ?? {}) as Record<string, unknown>;
      const customTopics = form.custom_research_topics
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const researchTopics = form.research_topics.map((topic) => ({
        name: researchTopicLabel(topic),
        parent_direction: researchDirectionLabel(researchTopicDirection(topic) ?? ""),
      }));
      const researchDirections = Array.from(new Set(form.research_topics.map((topic) => researchDirectionLabel(researchTopicDirection(topic) ?? "")).filter(Boolean)));
      const keywords = form.keywords
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const location = {
        country_code: form.country,
        country_name: optionLabel(countries, form.country),
        region: optionLabel(provinces, form.province),
        city: optionLabel(districts, form.district),
        coordinates: {},
      };

      const requirements = (cleanDetails.requirements_and_timeline ?? {}) as Record<string, unknown>;
      const trl = toNumberOrNull(requirements.technology_readiness_level);
      const budget = ((requirements.budget ?? {}) as Record<string, unknown>).amount;

      const response = await api.createProject({
        title: form.title,
        summary: form.summary,
        description: form.description,
        field: researchDirections[0] ?? "",
        status: form.status,
        budget: toNumberOrNull(budget),
        trl: trl === null ? null : trl,
        location: [location.city, location.region, location.country_name].filter(Boolean).join(", "),
        keywords,
        basic_info: {
          ...((cleanDetails.basic_info ?? {}) as Record<string, unknown>),
          title: form.title,
          description: form.description,
          research_directions: researchDirections,
          research_topics: [...researchTopics, ...customTopics.map((name) => ({ name, parent_direction: "Custom" }))],
          keywords,
          location,
          status: form.status,
          update_date: new Date().toISOString().slice(0, 10),
        },
        requirements_and_timeline: requirements,
        rd_profile: cleanDetails.rd_profile as Record<string, unknown> | undefined,
        relations: cleanDetails.relations as Record<string, unknown> | undefined,
        follow_up_opportunities: cleanDetails.follow_up_opportunities as Record<string, unknown> | undefined,
        governance: cleanDetails.governance as Record<string, unknown> | undefined,
      });
      router.push(`/projects/${response.data.id}/overview`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tạo project thất bại");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-svh bg-slate-50">
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-7 rounded-3xl border bg-white p-6 shadow-sm">
          <Badge variant="outline" className="rounded-full">
            <CalendarDays className="mr-2 h-3.5 w-3.5" />
            Project schema từ seed_data.txt
          </Badge>
          <h1 className="mt-4 text-3xl font-bold tracking-tight">Tạo project mới</h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Form này cho phép nhập các nhóm thông tin đầy đủ như dữ liệu mẫu: basic_info, requirements, R&D profile,
            relations, follow-up opportunities và governance. Không bắt buộc nhập hết, nhưng các trường topic/skill/TRL
            sẽ giúp recommendation tốt hơn.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <section className="rounded-3xl border bg-white p-6 shadow-sm">
            <div className="mb-5">
              <h2 className="text-xl font-bold">Basic info</h2>
              <p className="text-sm text-muted-foreground">Thông tin chính để frontend, MongoDB và KG nhận diện project.</p>
            </div>
            <div className="grid gap-5 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label>Tên project</Label>
                <Input required value={form.title} onChange={(event) => updateForm({ title: event.target.value })} placeholder="AI for Healthcare: Chest X-Ray Anomaly Detection" />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label>Tóm tắt</Label>
                <Textarea required rows={3} value={form.summary} onChange={(event) => updateForm({ summary: event.target.value })} />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label>Mô tả chi tiết</Label>
                <Textarea rows={6} value={form.description} onChange={(event) => updateForm({ description: event.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Trạng thái</Label>
                <Select value={form.status} onValueChange={(value) => updateForm({ status: value })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {statusOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Từ khóa</Label>
                <Input value={form.keywords} onChange={(event) => updateForm({ keywords: event.target.value })} placeholder="AI, X-Ray, Deep Learning, Healthcare" />
                <p className="text-xs text-muted-foreground">Cách nhau bằng dấu phẩy.</p>
              </div>
              <div className="space-y-2">
                <Label>Quốc gia</Label>
                <Select
                  value={form.country}
                  onValueChange={(value) => {
                    const nextProvince = firstProvince(value);
                    updateForm({ country: value, province: nextProvince, district: firstDistrict(value, nextProvince) });
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {countries.map((country) => (
                      <SelectItem key={country.value} value={country.value}>
                        {country.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Tỉnh / thành</Label>
                <Select
                  value={form.province}
                  onValueChange={(value) => updateForm({ province: value, district: firstDistrict(form.country, value) })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {provinces.map((province) => (
                      <SelectItem key={province.value} value={province.value}>
                        {province.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label>Quận / huyện / thành phố</Label>
                <Select value={form.district} onValueChange={(value) => updateForm({ district: value })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {districts.map((district) => (
                      <SelectItem key={district.value} value={district.value}>
                        {district.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-3 md:col-span-2">
                <div>
                  <Label>Chủ đề nghiên cứu</Label>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Hệ thống tự suy ra research_directions từ topic đã chọn:{" "}
                    {selectedDirections.length ? selectedDirections.map(researchDirectionLabel).join(", ") : "chưa chọn"}
                  </p>
                </div>
                <div className="space-y-4 rounded-2xl border bg-slate-50 p-4">
                  {topicGroups.map((group) => (
                    <div key={group.value} className="rounded-2xl border bg-white p-4">
                      <div className="mb-3 text-sm font-semibold">{group.label}</div>
                      <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                        {group.topics.map((topic) => (
                          <button
                            type="button"
                            key={topic.value}
                            onClick={() => toggleTopic(topic.value)}
                            className={`rounded-xl border p-3 text-left text-sm transition ${
                              form.research_topics.includes(topic.value)
                                ? "border-primary bg-primary/10 text-primary"
                                : "bg-white hover:bg-muted"
                            }`}
                          >
                            <span className="block font-medium">{topic.label}</span>
                            <span className="mt-1 block text-xs text-muted-foreground">{researchDirectionLabel(topic.direction)}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  <Label>Chủ đề khác</Label>
                  <Input value={form.custom_research_topics} onChange={(event) => updateForm({ custom_research_topics: event.target.value })} placeholder="Federated Learning, Digital Twin..." />
                  <p className="text-xs text-muted-foreground">Chủ đề khác được lưu với parent_direction = Custom để admin map vào taxonomy sau.</p>
                </div>
              </div>
            </div>
          </section>

          {projectSections.map((section) => (
            <section key={section.title} className="rounded-3xl border bg-white p-6 shadow-sm">
              <div className="mb-5">
                <h2 className="text-xl font-bold">{section.title}</h2>
                {section.description ? <p className="mt-1 text-sm text-muted-foreground">{section.description}</p> : null}
              </div>
              <div className="grid gap-5 md:grid-cols-2">{section.fields.map(renderField)}</div>
            </section>
          ))}

          {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div> : null}

          <div className="sticky bottom-4 z-10 flex justify-end rounded-3xl border bg-white/90 p-4 shadow-lg backdrop-blur">
            <Button type="submit" disabled={saving} size="lg">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Tạo project
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}
