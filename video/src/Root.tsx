import { Composition } from "remotion";
import { FPS, TOTAL_FRAMES, TunaRAGVideo } from "./Video";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TunaRAG"
      component={TunaRAGVideo}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={1920}
      height={1080}
    />
  );
};
