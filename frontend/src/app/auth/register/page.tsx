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
    label: "Chuyen gia",
    description: "Ho so ca nhan de tim project, doi tac va chuyen gia lien quan.",
    icon: UserCheck,
  },
  {
    value: "enterprise",
    label: "Doanh nghiep",
    description: "Ho so don vi de tim chuyen gia, project va co hoi hop tac R&D.",
    icon: Building2,
  },
  {
    value: "funder",
    label: "Nha tai tro",
    description: "Ho so quy/to chuc tai tro de tim project va linh vuc phu hop.",
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
      if (!form.full_name.trim()) return "Nhap ho ten hoac ten don vi.";
      if (!form.email.trim()) return "Nhap email.";
      if (form.password.length < 6) return "Mat khau can it nhat 6 ky tu.";
      if (form.password !== form.confirm_password) return "Mat khau xac nhan khong khop.";
    }
    if (
      nextStep === 2 &&
      selectedSkills.length === 0 &&
      (!useCustomSkill || form.custom_skills.trim().length === 0)
    ) {
      return "Chon it nhat mot ky nang/chuyen mon hoac nhap ky nang Khac.";
    }
    if (nextStep === 2 && (!form.country || !form.province || !form.district)) {
      return "Chon day du quoc gia, tinh/thanh va quan/huyen.";
    }
    if (nextStep === 3 && selectedTopics.length === 0 && (!useCustomTopic || form.custom_research_topics.trim().length === 0)) {
      return "Chon it nhat mot chu de nghien cuu hoac nhap chu de Khac.";
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
      setError(err instanceof Error ? err.message : "Dang ky that bai");
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
            Account onboarding
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight">Tao tai khoan</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Dang ky chi thu thap nhung thong tin can thiet de tao account, link entity va goi y ban dau. Cac thong tin
            chi tiet se bo sung trong Profile sau.
          </p>

          <div className="mt-6 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Buoc {step + 1}/4</span>
              <span className="text-muted-foreground">{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} />
          </div>

          <div className="mt-6 space-y-3 text-sm">
            {["Chon doi tuong", "Thong tin bat buoc", "Skill & location", "Chu de nghien cuu"].map((label, index) => (
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
            Da co tai khoan? Dang nhap
          </Link>
        </aside>

        <form onSubmit={handleRegister} className="register-reveal rounded-md border bg-white p-5">
          <div className="register-step min-h-[520px]">
            {step === 0 ? (
              <section className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold">Ban tham gia he thong voi vai tro nao?</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Vai tro nay dung de tao/link entity nghiep vu trong MongoDB va sync provisional vao Knowledge Graph.
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
                  <h2 className="text-2xl font-bold">Thong tin bat buoc</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Chi lay thong tin can de tao account, chong duplicate va tao entity ban dau. Phone, dia chi, mo ta,
                    identifier se bo sung trong Profile.
                  </p>
                </div>

                <Card className="rounded-md">
                  <CardContent className="grid gap-4 p-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="full_name">
                        {form.role === "expert" ? "Ho ten" : "Ten don vi"}
                      </Label>
                      <Input
                        id="full_name"
                        value={form.full_name}
                        onChange={(event) => updateForm("full_name", event.target.value)}
                        placeholder={form.role === "expert" ? "VD: Nguyen Van A" : "VD: TechMed Solutions"}
                        required
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="organization">To chuc truc thuoc</Label>
                      <Input
                        id="organization"
                        value={form.organization}
                        onChange={(event) => updateForm("organization", event.target.value)}
                        placeholder="Truong/Vien/Cong ty/Quy tai tro"
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
                      <Label>Social / academic links</Label>
                      <p className="text-xs text-muted-foreground">
                        Optional. He thong co the dung cac link nay de tu dong lay/enrich data ho so sau.
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
                      <Label htmlFor="password">Mat khau</Label>
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
                      <Label htmlFor="confirm_password">Xac nhan mat khau</Label>
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
                  <h2 className="text-2xl font-bold">Ky nang va dia diem</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Skill va location la cac relation quan trong de PGPR/XAI tim duong noi giua user, project, expert va enterprise.
                  </p>
                </div>

                <div className="rounded-md border p-4">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">Ky nang / chuyen mon</div>
                      <div className="text-sm text-muted-foreground">Chon nhung ky nang phu hop nhat voi ho so cua ban.</div>
                    </div>
                    <Badge variant="outline" className="rounded-md">
                      {selectedSkills.length} selected
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
                      Khac
                    </label>
                  </div>
                </div>

                {useCustomSkill ? (
                  <div className="space-y-2 rounded-md border bg-amber-50 p-4">
                    <Label htmlFor="custom_skills">Ky nang khac</Label>
                    <Input
                      id="custom_skills"
                      value={form.custom_skills}
                      onChange={(event) => updateForm("custom_skills", event.target.value)}
                      placeholder="Vi du: MLOps, GIS, Bioinformatics"
                    />
                    <p className="text-xs text-muted-foreground">
                      Ky nang custom duoc luu rieng va sync vao KG o dang provisional de admin co the chuan hoa sau.
                    </p>
                  </div>
                ) : null}

                <div className="grid gap-4 rounded-md border p-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <Label>Country</Label>
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
                    <Label>Tinh / Thanh</Label>
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
                    <Label>Quan / Huyen</Label>
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
                  <h2 className="text-2xl font-bold">Chu de nghien cuu / linh vuc quan tam</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Day la du lieu quan trong nhat de he thong tao relation voi Knowledge Graph va chay recommendation
                    ngay sau khi dang ky.
                  </p>
                </div>

                <div className="rounded-md border p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">Danh muc chuan cua he thong</div>
                      <div className="text-sm text-muted-foreground">Dang ky voi vai tro: {currentRole.label}</div>
                    </div>
                    <Badge variant="outline" className="rounded-md">
                      {selectedTopics.length} selected
                    </Badge>
                  </div>
                  {selectedDirections.length ? (
                    <div className="rounded-md border bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                      Huong nghien cuu tu dong nhan dien: {selectedDirections.map(researchDirectionLabel).join(", ")}
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
                      Khac
                    </label>
                  </div>
                </div>

                {useCustomTopic ? (
                  <div className="space-y-2 rounded-md border bg-amber-50 p-4">
                    <Label htmlFor="custom_research_topics">Chu de khac</Label>
                    <Input
                      id="custom_research_topics"
                      value={form.custom_research_topics}
                      onChange={(event) => updateForm("custom_research_topics", event.target.value)}
                      placeholder="Vi du: Federated Learning, Digital Twin"
                    />
                    <p className="text-xs text-muted-foreground">
                      Chu de custom se duoc luu rieng trong MongoDB va can admin map sang topic chuan truoc khi sync
                      public vao KG.
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
              Quay lai
            </Button>

            {step < 3 ? (
              <Button type="button" onClick={goNext}>
                Tiep tuc
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" disabled={loading}>
                {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Tao tai khoan
              </Button>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
