import { Composition } from "remotion";

import { Demo, DURATION } from "./Demo";
import { FPS } from "./timeline";

export const RemotionRoot: React.FC = () => {
  return <Composition id="RadsmartDemo" component={Demo} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />;
};
