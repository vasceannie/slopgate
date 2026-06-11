interface Props {
	data: number[];
	width?: number;
	height?: number;
	color?: string;
	className?: string;
}

export function Sparkline({
	data,
	width = 60,
	height = 20,
	color = "hsl(142, 50%, 45%)",
	className,
}: Props) {
	if (data.length < 2) return null;

	const max = Math.max(...data, 1);
	const min = Math.min(...data, 0);
	const range = max - min || 1;

	const points = data
		.map((v, i) => {
			const x = (i / (data.length - 1)) * width;
			const y = height - ((v - min) / range) * (height - 2) - 1;
			return `${x},${y}`;
		})
		.join(" ");

	// Area fill
	const areaPoints = `0,${height} ${points} ${width},${height}`;

	return (
		<svg
			aria-label="Sparkline trend"
			role="img"
			width={width}
			height={height}
			className={className}
			viewBox={`0 0 ${width} ${height}`}
		>
			<polygon points={areaPoints} fill={color} opacity={0.15} />
			<polyline
				points={points}
				fill="none"
				stroke={color}
				strokeWidth={1.5}
				strokeLinejoin="round"
				strokeLinecap="round"
			/>
		</svg>
	);
}
