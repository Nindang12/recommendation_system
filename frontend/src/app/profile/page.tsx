
'use client';

import { useState } from 'react';
import { Navbar } from '@/components/navigation/navbar';
import { USER_PROFILE } from '@/lib/mock-data';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import {X, User, MapPin, Globe, Phone, Mail, Save, Calendar, ShieldCheck } from 'lucide-react';

export default function ProfilePage() {
  const { toast } = useToast();
  const [profile, setProfile] = useState(USER_PROFILE);
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = () => {
    setIsSaving(true);
    setTimeout(() => {
      setIsSaving(false);
      toast({
        title: "Profile updated",
        description: "Your personalized recommendations will be refreshed shortly."
      });
    }, 1000);
  };

  return (
    <div className="min-h-svh bg-background flex flex-col">
      <Navbar />
      
      <main className="flex-1 container mx-auto px-4 py-8">
        <div className="max-w-5xl mx-auto">
          <header className="mb-12 border-b-2 border-black pb-8 flex items-end justify-between">
            <div className="space-y-4">
              <div className="w-24 h-24 bg-black text-white flex items-center justify-center font-headline font-bold text-4xl">
                {profile.fullName.charAt(0)}
              </div>
              <div>
                <h1 className="text-4xl font-headline font-bold uppercase tracking-tighter">{profile.fullName}</h1>
                <p className="text-muted-foreground font-medium">@{profile.username} • Knowledge Explorer</p>
              </div>
            </div>
            <Button onClick={handleSave} disabled={isSaving} className="gap-2 font-bold h-12 px-8">
              {isSaving ? "SAVING..." : <><Save className="w-4 h-4" /> SAVE CHANGES</>}
            </Button>
          </header>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
            <div className="lg:col-span-2 space-y-12">
              <section className="space-y-6">
                <h2 className="text-xl font-headline font-bold uppercase tracking-widest border-b pb-2 flex items-center gap-2">
                  <User className="w-5 h-5" /> Account Identity
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label>Full Name</Label>
                    <Input value={profile.fullName} onChange={(e) => setProfile({...profile, fullName: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Username</Label>
                    <Input value={profile.username} onChange={(e) => setProfile({...profile, username: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Birthday</Label>
                    <div className="relative">
                      <Input type="date" value={profile.birthday} onChange={(e) => setProfile({...profile, birthday: e.target.value})} />
                      <Calendar className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Gender</Label>
                    <Input value={profile.gender} onChange={(e) => setProfile({...profile, gender: e.target.value})} />
                  </div>
                </div>
              </section>

              <section className="space-y-6">
                <h2 className="text-xl font-headline font-bold uppercase tracking-widest border-b pb-2 flex items-center gap-2">
                  <Mail className="w-5 h-5" /> Contact Details
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label>Email Address</Label>
                    <div className="relative">
                      <Input value={profile.email} onChange={(e) => setProfile({...profile, email: e.target.value})} />
                      <Mail className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Phone Number</Label>
                    <div className="relative">
                      <Input value={profile.phone} onChange={(e) => setProfile({...profile, phone: e.target.value})} />
                      <Phone className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                    </div>
                  </div>
                  <div className="md:col-span-2 space-y-2">
                    <Label>Address</Label>
                    <div className="relative">
                      <Input value={profile.address} onChange={(e) => setProfile({...profile, address: e.target.value})} />
                      <MapPin className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                    </div>
                  </div>
                </div>
              </section>

              <section className="space-y-6">
                <h2 className="text-xl font-headline font-bold uppercase tracking-widest border-b pb-2 flex items-center gap-2">
                  <Globe className="w-5 h-5" /> Localization
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <Label>Nationality</Label>
                    <Input value={profile.nationality} onChange={(e) => setProfile({...profile, nationality: e.target.value})} />
                  </div>
                  <div className="space-y-2">
                    <Label>Language</Label>
                    <Input value={profile.language} onChange={(e) => setProfile({...profile, language: e.target.value})} />
                  </div>
                </div>
              </section>
            </div>

            <aside className="space-y-8">
              <div className="bg-black text-white p-8 space-y-6">
                <h3 className="font-headline font-bold uppercase tracking-widest text-sm border-b border-white/20 pb-2">GRAPH PREFERENCES</h3>
                <div className="space-y-4">
                  <p className="text-xs text-white/70 leading-relaxed italic">
                    These topics define your personalized feed and AI recommendations.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {profile.preferences.map(pref => (
                      <div key={pref} className="bg-white text-black px-3 py-1 text-xs font-bold uppercase tracking-wider flex items-center gap-2">
                        {pref} <X className="w-3 h-3 cursor-pointer" />
                      </div>
                    ))}
                    <Button variant="outline" size="sm" className="bg-transparent border-white text-white hover:bg-white hover:text-black text-[10px] uppercase font-bold">
                      + ADD TOPIC
                    </Button>
                  </div>
                </div>
              </div>

              <div className="border-2 border-black p-8 space-y-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5" />
                  <h3 className="font-headline font-bold uppercase tracking-widest text-sm">SECURITY</h3>
                </div>
                <p className="text-xs text-muted-foreground">Your account is secured with two-factor authentication.</p>
                <Button variant="outline" className="w-full font-bold uppercase text-[10px] tracking-widest">CHANGE PASSWORD</Button>
                <Button variant="link" className="w-full text-destructive text-xs font-bold uppercase tracking-widest">DEACTIVATE ACCOUNT</Button>
              </div>
            </aside>
          </div>
        </div>
      </main>
    </div>
  );
}
