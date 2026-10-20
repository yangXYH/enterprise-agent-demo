import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  paramsSerializer: { indexes: null },
})

const stringifyDetail = (detail: unknown): string => {
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => stringifyDetail(item))
      .filter(Boolean)
      .join('; ')
  }

  if (detail && typeof detail === 'object') {
    if ('msg' in detail && typeof detail.msg === 'string') {
      return detail.msg
    }

    if ('message' in detail && typeof detail.message === 'string') {
      return detail.message
    }

    return JSON.stringify(detail)
  }

  return ''
}

const getErrorMessage = (data: unknown): string => {
  if (!data || typeof data !== 'object') {
    return ''
  }

  if ('message' in data && typeof data.message === 'string') {
    return data.message
  }

  if ('detail' in data) {
    const detailMessage = stringifyDetail(data.detail)

    if (detailMessage) {
      return detailMessage
    }
  }

  if ('error' in data && typeof data.error === 'string') {
    return data.error
  }

  return ''
}

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const isSilent = error.config?.silent
    if (!isSilent) {
      const message = getErrorMessage(error.response?.data) || error.message || '请求失败'
      ElMessage.error(message)
    }
    return Promise.reject(error)
  },
)

export default request
