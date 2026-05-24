
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sparkles, Check, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';

const ONBOARDING_DATA = {
  industries: [
    'Technology', 'Healthcare', 'Energy', 'Finance', 'Logistics', 
    'Aerospace', 'Education', 'Biotechnology', 'Real Estate'
  ],
  expertise: [
    'Artificial Intelligence', 'Blockchain', 'Quantum Computing', 
    'Renewable Energy', 'Genetic Engineering', 'Cybersecurity', 
    'Sustainable Architecture', 'Macroeconomics'
  ],
  topics: [
    'Neural Networks', 'Carbon Capture', 'DeFi', 'Circular Economy', 
    'Personalized Medicine', 'Space Exploration', 'Climate Policy'
  ]
};

export default function OnboardingPage() {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const toggleItem = (item: string) => {
    setSelected(prev => 
      prev.includes(item) ? prev.filter(i => i !== item) : [...prev, item]
    );
  };

  const handleComplete = () => {
    setLoading(true);
    setTimeout(() => {
      router.push('/dashboard');
    }, 1200);
  };

  const Section = ({ title, items }: { title: string, items: string[] }) => (
    <div className="space-y-4">
      <h2 className="font-headline font-bold text-sm uppercase tracking-widest border-b border-black/10 pb-2">{title}</h2>
      <div className="flex flex-wrap gap-2">
        {items.map(item => {
          const isSelected = selected.includes(item);
          return (
            <button
              key={item}
              onClick={() => toggleItem(item)}
              className={cn(
                "px-4 py-2 text-xs font-bold uppercase tracking-wider border-2 transition-all",
                isSelected 
                  ? "bg-black text-white border-black" 
                  : "bg-transparent text-muted-foreground border-black/10 hover:border-black hover:text-black"
              )}
            >
              <div className="flex items-center gap-2">
                {item}
                {isSelected && <Check className="w-3 h-3" />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="min-h-svh bg-background py-12 px-4">
      <div className="max-w-4xl mx-auto space-y-12">
        <header className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-black text-white text-[10px] font-bold tracking-[0.3em] uppercase">
            <Sparkles className="w-3 h-3" /> Step 2: Fine-tune Discovery
          </div>
          <h1 className="text-5xl font-headline font-bold tracking-tighter">WHAT MOVES YOU?</h1>
          <p className="text-muted-foreground max-w-xl mx-auto uppercase text-xs font-bold tracking-widest">
            Select at least 3 topics to personalize your Knowledge Graph experience
          </p>
        </header>

        <div className="space-y-12">
          <Section title="Industries" items={ONBOARDING_DATA.industries} />
          <Section title="Areas of Expertise" items={ONBOARDING_DATA.expertise} />
          <Section title="Research Topics" items={ONBOARDING_DATA.topics} />
        </div>

        <div className="pt-12 border-t-2 border-black flex flex-col items-center gap-6">
          <div className="flex items-center gap-4 text-sm font-bold uppercase tracking-widest">
            <span className="text-muted-foreground">Selected:</span>
            <span>{selected.length} nodes</span>
          </div>
          
          <Button 
            onClick={handleComplete} 
            disabled={selected.length < 3 || loading}
            className="w-full max-w-md h-16 text-xl font-bold uppercase tracking-[0.2em] group"
          >
            {loading ? "CONFIGURING GRAPH..." : (
              <span className="flex items-center gap-3">
                FINALIZE PROFILE <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </span>
            )}
          </Button>
          
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest">
            You can always modify these preferences in your settings later.
          </p>
        </div>
      </div>
    </div>
  );
}
