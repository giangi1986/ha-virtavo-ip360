import importlib.util
import pathlib
import unittest

P = pathlib.Path(__file__).resolve().parents[1] / 'custom_components/virtavo/engine/video_pipeline.py'
spec = importlib.util.spec_from_file_location('virtavo_video_pipeline', P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class VideoPipelineTests(unittest.TestCase):
    def test_mpegts_stdout_and_copy(self):
        args = mod.ffmpeg_args('hevc', output='mpegts')
        self.assertEqual(args[-1], 'pipe:1')
        self.assertIn('copy', args)
        self.assertIn('-an', args)
        self.assertNotIn('libx265', args)
    def test_h264(self):
        args = mod.ffmpeg_args('h264', output='mpegts')
        self.assertIn('h264', args)
    def test_rtsp(self):
        args = mod.ffmpeg_args('hevc', output='rtsp', rtsp_url='rtsp://127.0.0.1:9999/test')
        self.assertEqual(args[-1], 'rtsp://127.0.0.1:9999/test')
    def test_reject_missing_server(self):
        with self.assertRaises(ValueError):
            mod.ffmpeg_args(output='rtsp')
    def test_reject_codec(self):
        with self.assertRaises(ValueError):
            mod.ffmpeg_args('vp9', output='mpegts')
    def test_reject_fps(self):
        with self.assertRaises(ValueError):
            mod.ffmpeg_args(output='mpegts', fps=0)

if __name__ == '__main__': unittest.main()
