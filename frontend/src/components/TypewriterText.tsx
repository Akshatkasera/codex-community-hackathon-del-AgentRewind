import { useEffect, useEffectEvent, useState } from 'react'

interface TypewriterTextProps {
  text: string
  speed?: number
}

export function TypewriterText({ text, speed = 14 }: TypewriterTextProps) {
  const [visibleChars, setVisibleChars] = useState(0)

  const tick = useEffectEvent(() => {
    setVisibleChars((current) => {
      if (current >= text.length) {
        return current
      }
      return current + 1
    })
  })

  useEffect(() => {
    if (!text) {
      return
    }

    const timer = window.setInterval(() => {
      tick()
    }, speed)

    return () => window.clearInterval(timer)
  }, [text, speed])

  return (
    <span>
      {text.slice(0, visibleChars)}
      {visibleChars < text.length ? <span className="typing-caret">█</span> : null}
    </span>
  )
}
