import { ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '../../lib/utils';

type ButtonVariant = 'default' | 'secondary' | 'ghost' | 'outline';
type ButtonSize = 'default' | 'sm' | 'icon';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

const variants: Record<ButtonVariant, string> = {
  default: 'bg-teal-700 text-white hover:bg-teal-800',
  secondary: 'bg-stone-100 text-stone-900 hover:bg-stone-200',
  ghost: 'bg-transparent text-stone-700 hover:bg-stone-100',
  outline: 'border border-stone-300 bg-white text-stone-900 hover:bg-stone-50',
};

const sizes: Record<ButtonSize, string> = {
  default: 'h-8 px-3',
  sm: 'h-7 px-2.5 text-xs',
  icon: 'h-8 w-8',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2',
        'disabled:pointer-events-none disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  ),
);

Button.displayName = 'Button';
