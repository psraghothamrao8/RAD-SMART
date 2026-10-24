import { Radiation } from "lucide-react";
import { lazy, Suspense } from "react";

// Keep heavy imports out of this module: it loads on every care_fe page, for every user.
const Today = lazy(() => import("./pages/Today"));
const Courses = lazy(() => import("./pages/Courses"));
const CourseNew = lazy(() => import("./pages/CourseNew"));
const CourseDetail = lazy(() => import("./pages/CourseDetail"));
const Breakdown = lazy(() => import("./pages/Breakdown"));
const Insights = lazy(() => import("./pages/Insights"));
const Messages = lazy(() => import("./pages/Messages"));
const CheckIn = lazy(() => import("./pages/CheckIn"));

/**
 * Structural mirrors of the host's prop types (care_fe/src/pluginTypes.ts).
 * Plugins are separate builds, so care_fe types cannot be imported.
 */
interface NavigationLink {
  url: string;
  name: string;
  icon?: React.ReactNode;
  children?: NavigationLink[];
}

type Params = Record<string, string>;

interface Manifest {
  plugin: string;
  routes: Record<string, (params: Params) => React.ReactNode>;
  extends: string[];
  components: {
    PatientInfoCardQuickActions: React.LazyExoticComponent<
      React.FC<{ encounter: { facility: { id: string }; patient: { id: string } }; className?: string }>
    >;
    PatientHomeActions: React.LazyExoticComponent<React.FC<{ patient: { id: string }; facilityId?: string; className?: string }>>;
    FacilityHomeActions: React.LazyExoticComponent<React.FC<{ facility: { id: string }; className?: string }>>;
  };
  navItems?: NavigationLink[];
  userNavItems?: NavigationLink[];
  adminNavItems?: NavigationLink[];
}

const page = (node: React.ReactNode) => <Suspense fallback={null}>{node}</Suspense>;

const manifest: Manifest = {
  plugin: "care_radsmart_fe",
  routes: {
    "/facility/:facilityId/radsmart": ({ facilityId }) => page(<Today facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/courses": ({ facilityId }) => page(<Courses facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/courses/new": ({ facilityId }) => page(<CourseNew facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/courses/:courseId": ({ facilityId, courseId }) =>
      page(<CourseDetail facilityId={facilityId} courseId={courseId} />),
    "/facility/:facilityId/radsmart/breakdown": ({ facilityId }) => page(<Breakdown facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/messages": ({ facilityId }) => page(<Messages facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/checkin": ({ facilityId }) => page(<CheckIn facilityId={facilityId} />),
    "/facility/:facilityId/radsmart/insights": ({ facilityId }) => page(<Insights facilityId={facilityId} />),
  },
  extends: [],
  components: {
    // The RADSMART button on the visit (encounter) page, beside the visit's own actions.
    PatientInfoCardQuickActions: lazy(() => import("./components/ext-encounter")),
    PatientHomeActions: lazy(() => import("./components/ext-patient")),
    FacilityHomeActions: lazy(() => import("./components/ext-facility")),
  },
  // Facility sidebar; the host prefixes /facility/{id}/.
  navItems: [{ url: "radsmart", name: "RAD-SMART", icon: <Radiation /> }],
  userNavItems: [],
  adminNavItems: [],
};

export default manifest;
