import dotenv from 'dotenv'


dotenv.config() /* Load env variables  */

const host = process.env.HOST 
const token = process.env.TOKEN

/* Try simple endpoint */
const response = await fetch(`${host}/api/users/`,{
    headers: {
        Authorization: `Bearer ${token}`
    }
})

const data = await response.json()

#console.log(data)