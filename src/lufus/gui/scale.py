from PySide6.QtWidgets import QApplication


class Scale:
    # base dpi for scaling calculations :D
    BASE_DPI = 80.0
    DESIGN_W = 750
    DESIGN_H = 1050
    REF_W = 2560
    REF_H = 1440

    def __init__(self, app: QApplication, factor: float = None):
        # get screen info for scaling
        screen = app.primaryScreen()
        logical_dpi = screen.logicalDotsPerInch()
        device_ratio = screen.devicePixelRatio()

        if factor is not None:
            # use custom factor if provided :3
            self._factor = max(factor, 0.3)
        else:
            # calculate factor from dpi
            self._factor = max(logical_dpi / self.BASE_DPI, 0.75)

        print(
            f"[Scale] logicalDPI={logical_dpi:.1f}  DevicePixelRatio={device_ratio:.2f}"
            f"  → scale factor={self._factor:.3f}"
        )

    def f(self) -> float:
        # return raw factor
        return self._factor

    def px(self, base_pixels: int | float) -> int:
        # scale pixels based on factor
        return max(1, round(base_pixels * self._factor))

    def pt(self, base_points: int | float) -> int:
        # scale font points based on factor :D
        return max(6, round(base_points * self._factor))
