// ECharts tree-shaking: only import needed components
import * as echarts from 'echarts/core'
import { CandlestickChart, BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  CandlestickChart,
  BarChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  LegendComponent,
  CanvasRenderer,
])

export default echarts
