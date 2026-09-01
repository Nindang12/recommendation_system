
'use client';

import Image from 'next/image';
import Link from 'next/link';
import { Entity } from '@/lib/mock-data';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Briefcase, UserCheck, Building2, TrendingUp, MapPin } from 'lucide-react';

const icons = {
  project: Briefcase,
  expert: UserCheck,
  enterprise: Building2,
  funder: TrendingUp,
};

export function EntityCard({ entity }: { entity: Entity }) {
  const Icon = icons[entity.type];

  return (
    <Link href={`/entities/${entity.type}/${entity.id}`}>
      <Card className="entity-card-hover h-full overflow-hidden border-border bg-card">
        <div className="relative aspect-video w-full">
          <Image
            src={entity.image}
            alt={entity.title}
            fill
            className="object-cover"
            data-ai-hint={entity.type === 'expert' ? 'professional portrait' : 'modern technology'}
          />
          <div className="absolute top-2 left-2">
            <Badge variant="secondary" className="bg-white/90 backdrop-blur-sm text-black flex items-center gap-1.5 uppercase text-[10px] tracking-widest font-bold">
              <Icon className="w-3 h-3" />
              {entity.type}
            </Badge>
          </div>
        </div>
        <CardHeader className="p-4 pb-2">
          <div className="space-y-1">
            <h3 className="font-headline text-lg font-bold leading-none">{entity.title}</h3>
            <p className="text-sm text-muted-foreground font-medium">{entity.subtitle}</p>
          </div>
        </CardHeader>
        <CardContent className="p-4 pt-0">
          <p className="text-sm line-clamp-2 text-muted-foreground">
            {entity.description}
          </p>
        </CardContent>
        <CardFooter className="p-4 pt-0 flex flex-wrap gap-2">
          {entity.location && (
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <MapPin className="w-3 h-3" />
              {entity.location}
            </div>
          )}
          <div className="w-full flex gap-1 mt-2">
            {entity.tags.slice(0, 2).map((tag) => (
              <Badge key={tag} variant="outline" className="text-[9px] px-1.5 py-0 uppercase">
                {tag}
              </Badge>
            ))}
          </div>
        </CardFooter>
      </Card>
    </Link>
  );
}
