// Iconos de Remix Icon (remixicon.com, licencia gratuita para uso comercial). Un nombre corto por icono: así el código no se llena de importaciones
// y, si un día se cambia de biblioteca, solo se toca este archivo. Siempre decorativos: el texto de al lado dice lo que significan.
import {
  RiAlertLine, RiArrowDownLine, RiArrowRightUpLine, RiArrowUpLine, RiBankCardLine, RiBarChartBoxLine, RiBillLine, RiBookOpenLine, RiCameraLine,
  RiCashLine, RiCheckLine, RiCheckboxCircleLine, RiCloseLine, RiDeleteBinLine, RiDownloadLine, RiEditBoxLine, RiFireLine, RiFlashlightLine,
  RiGiftLine, RiGlobalLine, RiHand, RiHeart3Fill, RiHourglassLine, RiLockLine, RiMoneyDollarCircleLine, RiNotification3Line, RiNotificationOffLine,
  RiPaletteLine, RiPauseCircleLine, RiPrinterLine, RiProhibitedLine, RiPuzzleLine, RiQrCodeLine, RiReceiptLine, RiRestaurantLine, RiRobot2Line, RiSettings3Line,
  RiSmartphoneLine, RiSparklingLine, RiStarFill, RiStarLine, RiTakeawayLine, RiTimeLine, RiUserLine,
} from "@remixicon/react";

const ICONS = {
  alert: RiAlertLine, down: RiArrowDownLine, ext: RiArrowRightUpLine, up: RiArrowUpLine, card: RiBankCardLine, chart: RiBarChartBoxLine,
  bill: RiBillLine, book: RiBookOpenLine, camera: RiCameraLine, cash: RiCashLine, check: RiCheckLine, checkc: RiCheckboxCircleLine,
  close: RiCloseLine, trash: RiDeleteBinLine, download: RiDownloadLine, note: RiEditBoxLine, fire: RiFireLine, bolt: RiFlashlightLine,
  gift: RiGiftLine, globe: RiGlobalLine, hand: RiHand, heart: RiHeart3Fill, hourglass: RiHourglassLine, lock: RiLockLine,
  money: RiMoneyDollarCircleLine, bell: RiNotification3Line, bellOff: RiNotificationOffLine, pause: RiPauseCircleLine, print: RiPrinterLine,
  ban: RiProhibitedLine, palette: RiPaletteLine, puzzle: RiPuzzleLine, qr: RiQrCodeLine, receipt: RiReceiptLine, menu: RiRestaurantLine, robot: RiRobot2Line,
  gear: RiSettings3Line, phone: RiSmartphoneLine, spark: RiSparklingLine, star: RiStarFill, starO: RiStarLine, takeaway: RiTakeawayLine,
  clock: RiTimeLine, user: RiUserLine,
} as const;

export type IconName = keyof typeof ICONS;

export default function Icon({ n, className }: { n: IconName; className?: string }) {
  const C = ICONS[n];
  return <C className={"ic" + (className ? " " + className : "")} aria-hidden="true" focusable="false" />;
}
