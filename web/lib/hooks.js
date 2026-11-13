'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { get } from './api'

// Gọi API định kỳ; trả {data, error, loading, reload}.
export function usePoll(path, interval = 0, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const alive = useRef(true)

  const reload = useCallback(async () => {
    if (!path) return
    try {
      const result = await get(path)
      if (alive.current) {
        setData(result)
        setError('')
      }
    } catch (err) {
      if (alive.current) setError(err.message)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    reload()
    if (!interval) return () => { alive.current = false }
    const timer = setInterval(reload, interval)
    return () => {
      alive.current = false
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, interval, ...deps])

  return { data, error, loading, reload, setData }
}

// Theo dõi job dài (kiểm tra hàng loạt, chạy Chrome): poll tới khi xong.
export function useJob(onFinish) {
  const [job, setJob] = useState(null)
  const timer = useRef(null)
  const finished = useRef(null)

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  const track = useCallback((initial) => {
    if (!initial || !initial.id) return
    setJob(initial)
    finished.current = null
    stop()
    timer.current = setInterval(async () => {
      try {
        const detail = await get(`/api/jobs/${initial.id}`)
        setJob(detail)
        if (detail.status !== 'running') {
          stop()
          if (finished.current !== detail.id) {
            finished.current = detail.id
            if (onFinish) onFinish(detail)
          }
        }
      } catch {
        stop()
      }
    }, 900)
  }, [onFinish, stop])

  useEffect(() => () => stop(), [stop])

  return { job, track, stop, setJob }
}

// Nhật ký realtime dùng con trỏ seq để chỉ lấy phần mới.
export function useLogs(interval = 2000) {
  const [lines, setLines] = useState([])
  const cursor = useRef(0)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const result = await get(`/api/logs?after=${cursor.current}`)
        if (!alive || !result) return
        cursor.current = result.cursor
        if (result.lines.length) {
          setLines((current) => [...result.lines, ...current].slice(0, 300))
        }
      } catch {
        /* API tắt thì thôi, lần sau thử lại */
      }
    }
    load()
    const timer = setInterval(load, interval)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [interval])

  return lines
}
