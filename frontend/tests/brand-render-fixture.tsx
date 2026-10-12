import { renderToStaticMarkup } from "react-dom/server";
import { BrandLogo } from "../components/brand-logo";
import { DashboardBrand } from "../components/dashboard/app-sidebar";

process.stdout.write(
  JSON.stringify({
    primary: renderToStaticMarkup(<BrandLogo />),
    accent: renderToStaticMarkup(<BrandLogo variant="accent" />),
    inverse: renderToStaticMarkup(<BrandLogo variant="inverse" />),
    dashboard: renderToStaticMarkup(<DashboardBrand />),
  }),
);
