import React, { useEffect, useState } from 'react'
import '../App.css';

export default function AppStats() {
    const [isLoaded, setIsLoaded] = useState(false);
    const [stats, setStats] = useState({});
    const [error, setError] = useState(null)

	const getStats = () => {
	
        fetch(`http://lab6kafka.canadacentral.cloudapp.azure.com/processing/stats`)
            .then(res => res.json())
            .then((result)=>{
				console.log("Received Stats")
                setStats(result);
                setIsLoaded(true);
            },(error) =>{
                setError(error)
                setIsLoaded(true);
            })
    }
    useEffect(() => {
		const interval = setInterval(() => getStats(), 2000); // Update every 2 seconds
		return() => clearInterval(interval);
    }, [getStats]);

    if (error){
        return (<div className={"error"}>Error found when fetching from API</div>)
    } else if (isLoaded === false){
        return(<div>Loading...</div>)
    } else if (isLoaded === true){
        return(
            <div>
                <h1>Latest Stats</h1>
                <table className={"StatsTable"}>
					<tbody>
						<tr>
							<th>Location</th>
							<th>Time-until-arrival</th>
						</tr>
						<tr>
							<td># Location: {stats['num_location_readings']}</td>
							<td># Time-until-arrival: {stats['num_time_until_arrival_readings']}</td>
						</tr>
						<tr>
							<td colSpan="2">Max Time-until-arrival: {stats['max_location_latitude_reading']}</td>
						</tr>
						<tr>
							<td colSpan="2">Max difference in arrival time: {stats['max_time_until_arrival_time_difference_in_ms_reading']}</td>
						</tr>
					</tbody>
                </table>
                <h3>Last Updated: {stats['last_updated']}</h3>
            </div>
        )
    }
}
