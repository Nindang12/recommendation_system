"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  Loader2,
  ShieldCheck,
  TrendingUp,
  UserCheck,
} from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import {
  countryOptions,
  districtOptions,
  firstDistrict,
  firstProvince,
  provinceOptions,
  skillOptions,
} from "@/lib/profile-options";
import { researchDirectionLabel, researchTopicDirection, researchTopicsByDirection } from "@/lib/research-topics";

gsap.registerPlugin(ScrollTrigger);

const roles = [
  {
    value: "expert",
    label: "Chuyên gia",
    description: "Hồ sơ cá nhân để tìm project, đối tác và chuyên gia liên quan.",
    icon: UserCheck,
  },
  {
    value: "enterprise",
    label: "Doanh nghiệp",
    description: "Hồ sơ đơn vị để tìm chuyên gia, project và cơ hội hợp tác R&D.",
    icon: Building2,
  },
  {
    value: "funder",
    label: "Nhà tài trợ",
    description: "Hồ sơ quỹ/tổ chức tài trợ để tìm project và lĩnh vực phù hợp.",
    icon: TrendingUp,
  },
] as const;

type RoleValue = (typeof roles)[number]["value"];

type RegisterForm = {
  role: RoleValue;
  full_name: string;
  organization: string;
  email: string;
  password: string;
  confirm_password: string;
  country: string;
  province: string;
  district: string;
  website_url: string;
  linkedin_url: string;
  google_scholar_url: string;
  orcid_url: string;
  custom_skills: string;
  custom_research_topics: string;
};

const initialForm: RegisterForm = {
  role: "expert",
  full_name: "",
  organization: "",
  email: "",
  password: "",
  confirm_password: "",
  country: "VN",
  province: firstProvince("VN"),
  district: firstDistrict("VN", firstProvince("VN")),
  website_url: "",
  linkedin_url: "",
  google_scholar_url: "",
  orcid_url: "",
  custom_skills: "",
  custom_research_topics: "",
};

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<RegisterForm>(initialForm);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [useCustomSkill, setUseCustomSkill] = useState(false);
  const [useCustomTopic, setUseCustomTopic] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const progress = ((step + 1) / 4) * 100;
  const currentRole = roles.find((role) => role.value === form.role) ?? roles[0];
  const countries = countryOptions();
  const provinces = provinceOptions(form.country);
  const districts = districtOptions(form.country, form.province);
  const topicGroups = researchTopicsByDirection();
  const selectedDirections = Array.from(
    new Set(selectedTopics.map((topic) => researchTopicDirection(topic)).filter(Boolean) as string[]),
  );

  useEffect(() => {
    const scope = rootRef.current;
    if (!scope) return;
    const context = gsap.context(() => {
      gsap.fromTo(
        ".register-reveal",
        { y: 28, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.6,
          ease: "power3.out",
          stagger: 0.06,
          scrollTrigger: {
            trigger: scope,
            start: "top 84%",
            once: true,
          },
        },
      );
      gsap.fromTo(
        ".register-step",
        { x: 24, opacity: 0 },
        { x: 0, opacity: 1, duration: 0.45, ease: "power2.out" },
      );
    }, scope);
    return () => context.revert();
  }, [step]);

  function updateForm(key: keyof RegisterForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function toggleTopic(topic: string, checked: boolean | "indeterminate") {
    setSelectedTopics((current) =>
      checked === true ? Array.from(new Set([...current, topic])) : current.filter((item) => item !== topic),
    );
  }

  function toggleSkill(skill: string, checked: boolean | "indeterminate") {
    setSelectedSkills((current) =>
      checked === true ? Array.from(new Set([...current, skill])) : current.filter((item) => item !== skill),
    );
  }

  function validateStep(nextStep = step) {
    if (nextStep === 1) {
      if (!form.full_name.trim()) return "Nhập họ tên hoặc tên đơn vị.";
      if (!form.email.trim()) return "Nhập email.";
      if (form.password.length < 6) return "Mật khẩu cần ít nhất 6 ký tự.";
      if (form.password !== form.confirm_password) return "Mật khẩu xác nhận không khớp.";
    }
    if (
      nextStep === 2 &&
      selectedSkills.length === 0 &&
      (!useCustomSkill || form.custom_skills.trim().length === 0)
    ) {
      return "Chọn ít nhất một kỹ năng/chuyên môn hoặc nhập Kỹ năng Khác.";
    }
    if (nextStep === 2 && (!form.country || !form.province || !form.district)) {
      return "Chọn đầy đủ quốc gia, tỉnh/thành và quận/huyện.";
    }
    if (nextStep === 3 && selectedTopics.length === 0 && (!useCustomTopic || form.custom_research_topics.trim().length === 0)) {
      return "Chọn ít nhất một chủ đề nghiên cứu hoặc nhập chủ đề Khác.";
    }
    return "";
  }

  function goNext() {
    const validationError = validateStep(step);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    setStep((current) => Math.min(current + 1, 3));
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateStep(3);
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError("");
    try {
      await register({
        email: form.email,
        password: form.password,
        full_name: form.full_name,
        username: "",
        role: form.role,
        organization: form.organization,
        phone: "",
        address: "",
        social_links: {
          website: form.website_url,
          linkedin: form.linkedin_url,
          google_scholar: form.google_scholar_url,
          orcid: form.orcid_url,
        },
        country: form.country,
        province: form.province,
        district: form.district,
        skills: selectedSkills,
        custom_skills: useCustomSkill
          ? form.custom_skills
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
        bio: "",
        research_interests: selectedTopics,
        custom_research_topics: useCustomTopic
          ? form.custom_research_topics
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
      });
      router.push("/profile");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng ký thất bại");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div ref={rootRef} className="min-h-svh bg-slate-50 px-4 py-8">
      <main className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[360px_1fr]">
        <aside className="register-reveal rounded-md border bg-white p-5 lg:sticky lg:top-6 lg:h-fit">
          <Badge variant="outline" className="mb-4 rounded-md gap-1">
            <ShieldCheck className="h-3.5 w-3.5" />
            Xác thực tài khoản
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight">Tạo tài khoản</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Đăng ký chỉ thu thập những thông tin cần thiết để tạo tài khoản, liên kết thực thể và gợi ý ban đầu. Các thông tin
            chi tiết sẽ bổ sung trong Hồ sơ sau.
          </p>

          <div className="mt-6 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Bước {step + 1}/4</span>
              <span className="text-muted-foreground">{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} />
          </div>

          <div className="mt-6 space-y-3 text-sm">
            {["Chọn đối tượng", "Thông tin bắt buộc", "Kỹ năng & địa điểm", "Chủ đề nghiên cứu"].map((label, index) => (
              <div key={label} className="flex items-center gap-3">
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-md border text-xs font-semibold ${
                    index <= step ? "border-slate-900 bg-slate-900 text-white" : "bg-white text-muted-foreground"
                  }`}
                >
                  {index < step ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
                </div>
                <span className={index === step ? "font-semibold" : "text-muted-foreground"}>{label}</span>
              </div>
            ))}
          </div>

          <Link href="/auth/login" className="mt-6 block text-sm text-muted-foreground hover:text-foreground">
            Đã có tài khoản? Đăng nhập
          </Link>
        </aside>

        <form onSubmit={handleRegister} className="register-reveal rounded-md border bg-white p-5">
          <div className="register-step min-h-[520px]">
            {step === 0 ? (
              <section className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold">Bạn tham gia hệ thống với vai trò nào?</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Vai trò này dùng để tạo/liên kết entity nghiệp vụ trong MongoDB và đồng bộ tạm thời vào Knowledge Graph.
                  </p>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  {roles.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => {
                        updateForm("role", item.value);
                        setError("");
                      }}
                      className={`min-h-[170px] rounded-md border p-4 text-left transition-colors ${
                        form.role === item.value
                          ? "border-slate-900 bg-slate-50 shadow-sm"
                          : "bg-white hover:border-slate-400"
                      }`}
                    >
                      <div className="flex h-11 w-11 items-center justify-center rounded-md bg-slate-100">
                        <item.icon className="h-5 w-5" />
                      </div>
                      <div className="mt-4 font-semibold">{item.label}</div>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</p>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            {step === 1 ? (
              <section className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold">Thông tin bắt buộc</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Chỉ lấy thông tin cần để tạo tài khoản, chống trùng và tạo entity ban đầu. Số điện thoại, địa chỉ, mô tả,
                    identifier sẽ bổ sung trong Hồ sơ.
                  </p>
                </div>

                <Card className="rounded-md">
                  <CardContent className="grid gap-4 p-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="full_name">
                        {form.role === "expert" ? "Họ tên" : "Tên đơn vị"}
                      </Label>
                      <Input
                        id="full_name"
                        value={form.full_name}
                        onChange={(event) => updateForm("full_name", event.target.value)}
                        placeholder={form.role === "expert" ? "VD: Nguyễn Văn A" : "VD: TechMed Solutions"}
                        required
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="organization">Tổ chức trực thuộc</Label>
                      <Input
                        id="organization"
                        value={form.organization}
                        onChange={(event) => updateForm("organization", event.target.value)}
                        placeholder="Trường/Viện/Công ty/Quỹ tài trợ"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="email">Email</Label>
                      <Input
                        id="email"
                        value={form.email}
                        onChange={(event) => updateForm("email", event.target.value)}
                        type="email"
                        placeholder="name@example.com"
                        required
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label>Liên kết xã hội / học thuật</Label>
                      <p className="text-xs text-muted-foreground">
                        Không bắt buộc. Hệ thống có thể sử dụng các link này để tự động lấy/thêm dữ liệu cho hồ sơ sau.
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="website_url">Website / profile URL</Label>
                      <Input
                        id="website_url"
                        value={form.website_url}
                        onChange={(event) => updateForm("website_url", event.target.value)}
                        placeholder="https://..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="linkedin_url">LinkedIn</Label>
                      <Input
                        id="linkedin_url"
                        value={form.linkedin_url}
                        onChange={(event) => updateForm("linkedin_url", event.target.value)}
                        placeholder="https://linkedin.com/in/..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="google_scholar_url">Google Scholar</Label>
                      <Input
                        id="google_scholar_url"
                        value={form.google_scholar_url}
                        onChange={(event) => updateForm("google_scholar_url", event.target.value)}
                        placeholder="https://scholar.google.com/..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="orcid_url">ORCID</Label>
                      <Input
                        id="orcid_url"
                        value={form.orcid_url}
                        onChange={(event) => updateForm("orcid_url", event.target.value)}
                        placeholder="https://orcid.org/..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="password">Mật khẩu</Label>
                      <Input
                        id="password"
                        value={form.password}
                        onChange={(event) => updateForm("password", event.target.value)}
                        type="password"
                        minLength={6}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="confirm_password">Xác nhận mật khẩu</Label>
                      <Input
                        id="confirm_password"
                        value={form.confirm_password}
                        onChange={(event) => updateForm("confirm_password", event.target.value)}
                        type="password"
                        minLength={6}
                        required
                      />
                    </div>
                  </CardContent>
                </Card>
              </section>
            ) : null}

            {step === 2 ? (
              <section className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold">Kỹ năng và địa điểm</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Kỹ năng và địa điểm là các liên kết quan trọng để PGPR/XAI tìm đường nối giữa user, project, chuyên gia và doanh nghiệp.
                  </p>
                </div>

                <div className="rounded-md border p-4">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">Kỹ năng / chuyên môn</div>
                      <div className="text-sm text-muted-foreground">Chọn những kỹ năng phù hợp nhất với hồ sơ của bạn.</div>
                    </div>
                    <Badge variant="outline" className="rounded-md">
                      {selectedSkills.length} đã chọn
                    </Badge>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {skillOptions.map((skill) => (
                      <label
                        key={skill.value}
                        className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border bg-slate-50 px-3 py-2 text-sm hover:border-slate-400"
                      >
                        <Checkbox
                          checked={selectedSkills.includes(skill.value)}
                          onCheckedChange={(checked) => toggleSkill(skill.value, checked)}
                        />
                        {skill.label}
                      </label>
                    ))}
                    <label className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border bg-slate-50 px-3 py-2 text-sm hover:border-slate-400">
                      <Checkbox checked={useCustomSkill} onCheckedChange={(checked) => setUseCustomSkill(checked === true)} />
                      Khác
                    </label>
                  </div>
                </div>

                {useCustomSkill ? (
                  <div className="space-y-2 rounded-md border bg-amber-50 p-4">
                    <Label htmlFor="custom_skills">Kỹ năng khác</Label>
                    <Input
                      id="custom_skills"
                      value={form.custom_skills}
                      onChange={(event) => updateForm("custom_skills", event.target.value)}
                      placeholder="Ví dụ: MLOps, GIS, Bioinformatics"
                    />
                    <p className="text-xs text-muted-foreground">
                      Kỹ năng custom sẽ được lưu riêng và đồng bộ vào KG ở dạng provisional để admin chuẩn hóa sau.
                    </p>
                  </div>
                ) : null}

                <div className="grid gap-4 rounded-md border p-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label>Quốc gia</Label>
                    <Select
                      value={form.country}
                      onValueChange={(value) => {
                        const nextProvince = firstProvince(value);
                        const nextDistrict = firstDistrict(value, nextProvince);
                        updateForm("country", value);
                        updateForm("province", nextProvince);
                        updateForm("district", nextDistrict);
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
                    <Label>Tỉnh / Thành</Label>
                    <Select
                      value={form.province}
                      onValueChange={(value) => {
                        const nextDistrict = firstDistrict(form.country, value);
                        updateForm("province", value);
                        updateForm("district", nextDistrict);
                      }}
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
                  <div className="space-y-2">
                    <Label>Quận / Huyện</Label>
                    <Select value={form.district} onValueChange={(value) => updateForm("district", value)}>
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
                </div>
              </section>
            ) : null}

            {step === 3 ? (
              <section className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold">Chủ đề nghiên cứu / lĩnh vực quan tâm</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Đây là dữ liệu quan trọng nhất để hệ thống tạo liên kết với Knowledge Graph và chạy đề xuất
                    ngay sau khi đăng ký.
                  </p>
                </div>

                <div className="rounded-md border p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">Danh mục chuẩn của hệ thống</div>
                      <div className="text-sm text-muted-foreground">Đăng ký với vai trò: {currentRole.label}</div>
                    </div>
                    <Badge variant="outline" className="rounded-md">
                      {selectedTopics.length} đã chọn
                    </Badge>
                  </div>
                  {selectedDirections.length ? (
                    <div className="rounded-md border bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                      Hướng nghiên cứu tự động nhận diện: {selectedDirections.map(researchDirectionLabel).join(", ")}
                    </div>
                  ) : null}
                  <div className="space-y-4">
                    {topicGroups.map((group) => (
                      <div key={group.value} className="rounded-md border bg-slate-50 p-3">
                        <div className="mb-3 text-xs font-semibold uppercase text-muted-foreground">{group.label}</div>
                        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                          {group.topics.map((topic) => (
                            <label
                              key={topic.value}
                              className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-2 text-sm hover:border-slate-400"
                            >
                              <Checkbox
                                checked={selectedTopics.includes(topic.value)}
                                onCheckedChange={(checked) => toggleTopic(topic.value, checked)}
                              />
                              <span>
                                <span className="block font-medium">{topic.label}</span>
                                <span className="block text-[11px] text-muted-foreground">
                                  {researchDirectionLabel(topic.direction)}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                    <label className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border bg-slate-50 px-3 py-2 text-sm hover:border-slate-400">
                      <Checkbox checked={useCustomTopic} onCheckedChange={(checked) => setUseCustomTopic(checked === true)} />
                      Khác
                    </label>
                  </div>
                </div>

                {useCustomTopic ? (
                  <div className="space-y-2 rounded-md border bg-amber-50 p-4">
                    <Label htmlFor="custom_research_topics">Chủ đề khác</Label>
                    <Input
                      id="custom_research_topics"
                      value={form.custom_research_topics}
                      onChange={(event) => updateForm("custom_research_topics", event.target.value)}
                      placeholder="Ví dụ: Federated Learning, Digital Twin"
                    />
                    <p className="text-xs text-muted-foreground">
                      Chủ đề custom sẽ được lưu riêng trong MongoDB và cần admin map sang chủ đề chuẩn trước khi đồng bộ
                      public vào KG.
                    </p>
                  </div>
                ) : null}
              </section>
            ) : null}
          </div>

          {error ? <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              disabled={step === 0 || loading}
              onClick={() => {
                setError("");
                setStep((current) => Math.max(current - 1, 0));
              }}
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              Quay lại
            </Button>

            {step < 3 ? (
              <Button type="button" onClick={goNext}>
                Tiếp tục
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Tạo tài khoản
              </Button>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
