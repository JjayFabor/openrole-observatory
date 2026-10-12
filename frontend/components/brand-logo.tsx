import Image from "next/image";
import { cn } from "@/lib/utils";

const wordmarks = {
  primary: "/brand/openrole-logo-v4.svg",
  accent: "/brand/openrole-logo-v4-accent.svg",
  inverse: "/brand/openrole-logo-v4-inverse.svg",
};

type BrandLogoProps = {
  variant?: keyof typeof wordmarks;
  className?: string;
};

export function BrandLogo({
  variant = "primary",
  className,
}: BrandLogoProps) {
  return (
    <Image
      src={wordmarks[variant]}
      alt="OpenRole"
      width={310}
      height={78}
      className={cn("h-auto w-[155px]", className)}
    />
  );
}
