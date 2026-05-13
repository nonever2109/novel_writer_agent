import * as TabsPrimitive from '@radix-ui/react-tabs';
import { ComponentPropsWithoutRef, ElementRef, forwardRef } from 'react';
import { cn } from '../../lib/utils';

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<
  ElementRef<typeof TabsPrimitive.List>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn('inline-flex h-8 items-center rounded-md bg-stone-100 p-1 text-stone-600', className)}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = forwardRef<
  ElementRef<typeof TabsPrimitive.Trigger>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'inline-flex h-6 items-center justify-center rounded px-2.5 text-xs font-medium transition-colors',
      'data-[state=active]:bg-white data-[state=active]:text-stone-950 data-[state=active]:shadow-sm',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700',
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = forwardRef<
  ElementRef<typeof TabsPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn('mt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700', className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;
