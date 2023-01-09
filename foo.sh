MSG="blabla [build:test]"
MSG="${MSG##*build:}"
DIR="${MSG%%]*}"

echo $DIR
