const FIELD = /^(\*|\d+(-\d+)?(,\d+(-\d+)?)*|\*\/\d+|\d+\/\d+)$/

export function isValidCron(expr: string): boolean {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return false
  const bounds: Array<[number, number]> = [
    [0, 59],
    [0, 23],
    [1, 31],
    [1, 12],
    [0, 7],
  ]
  return fields.every((field, i) => {
    if (!FIELD.test(field)) return false
    const numbers = field.match(/\d+/g) ?? []
    if (field.startsWith('*/')) {
      const step = Number(numbers[0])
      return step >= 1
    }
    return numbers.every(
      (n) => Number(n) >= bounds[i][0] && Number(n) <= bounds[i][1],
    )
  })
}

export function describeCron(expr: string): string {
  if (!isValidCron(expr)) return expr
  const [minute, hour, dom, month, dow] = expr.trim().split(/\s+/)
  const rest = [dom, month, dow]
  if (rest.every((f) => f === '*')) {
    const everyN = minute.match(/^\*\/(\d+)$/)
    if (everyN && hour === '*') return `every ${everyN[1]} min`
    if (minute === '0' && hour === '*') return 'hourly'
    if (/^\d+$/.test(minute) && hour === '*')
      return `hourly at :${minute.padStart(2, '0')}`
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour))
      return `daily at ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
    const everyH = hour.match(/^\*\/(\d+)$/)
    if (everyH && minute === '0') return `every ${everyH[1]} h`
  }
  return expr
}
