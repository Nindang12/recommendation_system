
'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Database, UserCheck, Building2, TrendingUp } from 'lucide-react';

export default function RegisterPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [userType, setUserType] = useState('expert');

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Redirect to onboarding instead of dashboard
    setTimeout(() => {
      router.push('/auth/onboarding');
    }, 1500);
  };

  return (
    <div className="min-h-svh py-12 px-4 bg-background">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center p-2 bg-black text-white mb-2">
            <Database className="w-6 h-6" />
          </div>
          <h1 className="text-3xl font-headline font-bold tracking-tighter uppercase">Join Knowledge Nexus</h1>
          <p className="text-muted-foreground text-sm uppercase tracking-widest font-medium">Select your entity type to begin</p>
        </div>

        <Tabs defaultValue="expert" className="w-full" onValueChange={setUserType}>
          <TabsList className="grid w-full grid-cols-3 h-16 bg-muted/50 rounded-none border-2 border-black p-1">
            <TabsTrigger value="expert" className="rounded-none data-[state=active]:bg-black data-[state=active]:text-white font-bold gap-2">
              <UserCheck className="w-4 h-4" /> EXPERT
            </TabsTrigger>
            <TabsTrigger value="enterprise" className="rounded-none data-[state=active]:bg-black data-[state=active]:text-white font-bold gap-2">
              <Building2 className="w-4 h-4" /> ENTERPRISE
            </TabsTrigger>
            <TabsTrigger value="funder" className="rounded-none data-[state=active]:bg-black data-[state=active]:text-white font-bold gap-2">
              <TrendingUp className="w-4 h-4" /> FUNDER
            </TabsTrigger>
          </TabsList>

          <form onSubmit={handleRegister} className="mt-8 space-y-10">
            <TabsContent value="expert" className="space-y-10 mt-0">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">PERSONAL IDENTITY</h2>
                  <div className="space-y-2">
                    <Label htmlFor="fullname">Full Name</Label>
                    <input id="fullname" placeholder="Dr. John Doe" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <input id="username" placeholder="johndoe_phd" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black" />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="gender">Gender</Label>
                      <Select>
                        <SelectTrigger id="gender" className="border-black">
                          <SelectValue placeholder="Select" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="male">Male</SelectItem>
                          <SelectItem value="female">Female</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="birthday">Birthday</Label>
                      <input id="birthday" type="date" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="specialty">Primary Specialty</Label>
                    <input id="specialty" placeholder="e.g. Artificial Intelligence" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>

                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">CONTACT & SECURITY</h2>
                  <div className="space-y-2">
                    <Label htmlFor="email">Professional Email</Label>
                    <input id="email" type="email" placeholder="name@university.edu" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <input id="phone" type="tel" placeholder="+1 234 567 890" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <input id="password" type="password" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm-password">Confirm Password</Label>
                    <input id="confirm-password" type="password" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="enterprise" className="space-y-10 mt-0">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">COMPANY DETAILS</h2>
                  <div className="space-y-2">
                    <Label htmlFor="company-name">Legal Company Name</Label>
                    <input id="company-name" placeholder="Nexus Dynamics Corp" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="industry">Industry Sector</Label>
                    <Select>
                      <SelectTrigger id="industry" className="border-black">
                        <SelectValue placeholder="Select Industry" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="tech">Technology</SelectItem>
                        <SelectItem value="healthcare">Healthcare</SelectItem>
                        <SelectItem value="finance">Finance</SelectItem>
                        <SelectItem value="energy">Renewable Energy</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="founded">Founded Year</Label>
                      <input id="founded" placeholder="2019" className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="size">Employee Count</Label>
                      <Select>
                        <SelectTrigger id="size" className="border-black">
                          <SelectValue placeholder="Select Range" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1-50">1-50</SelectItem>
                          <SelectItem value="51-200">51-200</SelectItem>
                          <SelectItem value="201-1000">201-1000</SelectItem>
                          <SelectItem value="1000+">1000+</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="website">Company Website</Label>
                    <input id="website" placeholder="https://company.com" className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>

                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">CORPORATE CONTACT</h2>
                  <div className="space-y-2">
                    <Label htmlFor="hq-address">Headquarters Address</Label>
                    <input id="hq-address" placeholder="123 Tech Plaza, Berlin, Germany" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="corp-email">Business Email</Label>
                    <input id="corp-email" type="email" placeholder="contact@company.com" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="corp-phone">Business Phone</Label>
                    <input id="corp-phone" type="tel" placeholder="+49 30 123456" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Account Password</Label>
                    <input id="password" type="password" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="funder" className="space-y-10 mt-0">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">FUND INFORMATION</h2>
                  <div className="space-y-2">
                    <Label htmlFor="org-name">Organization Name</Label>
                    <input id="org-name" placeholder="Green Horizon Capital" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fund-type">Fund Type</Label>
                    <Select>
                      <SelectTrigger id="fund-type" className="border-black">
                        <SelectValue placeholder="Select Type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="vc">Venture Capital</SelectItem>
                        <SelectItem value="angel">Angel Network</SelectItem>
                        <SelectItem value="pe">Private Equity</SelectItem>
                        <SelectItem value="gov">Government/Grant</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="check-size">Typical Check Size</Label>
                    <Select>
                      <SelectTrigger id="check-size" className="border-black">
                        <SelectValue placeholder="Select Range" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="100k-500k">$100K - $500K</SelectItem>
                        <SelectItem value="500k-2m">$500K - $2M</SelectItem>
                        <SelectItem value="2m-10m">$2M - $10M</SelectItem>
                        <SelectItem value="10m+">$10M+</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="focus">Focus Sectors</Label>
                    <input id="focus" placeholder="e.g. Climate Tech, BioTech" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>

                <div className="space-y-4">
                  <h2 className="font-headline text-lg font-bold border-b-2 border-black pb-2">INVESTOR RELATIONS</h2>
                  <div className="space-y-2">
                    <Label htmlFor="portfolio">Portfolio URL</Label>
                    <input id="portfolio" placeholder="https://fund.com/portfolio" className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="funder-email">Contact Email</Label>
                    <input id="funder-email" type="email" placeholder="invest@fund.com" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="funder-phone">Phone Number</Label>
                    <input id="funder-phone" type="tel" placeholder="+1 555-FUND" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <input id="password" type="password" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="confirm-password">Confirm Password</Label>
                    <input id="confirm-password" type="password" required className="flex h-10 w-full rounded-md border border-black bg-background px-3 py-2 text-sm" />
                  </div>
                </div>
              </div>
            </TabsContent>

            <div className="flex flex-col items-center gap-4 border-t-2 border-black pt-8">
              <Button type="submit" className="w-full max-w-sm h-14 text-lg font-bold uppercase tracking-widest" disabled={loading}>
                {loading ? "PROCESSING..." : `REGISTER AS ${userType}`}
              </Button>
              <p className="text-sm text-muted-foreground">
                Already part of the network?{' '}
                <Link href="/auth/login" className="text-black font-bold hover:underline">
                  Sign in here
                </Link>
              </p>
            </div>
          </form>
        </Tabs>
      </div>
    </div>
  );
}
