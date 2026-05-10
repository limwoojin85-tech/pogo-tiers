package com.woojin.pokemanager.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface PokemonDao {
    @Query("SELECT * FROM my_pokemon ORDER BY capturedAt DESC")
    fun getAll(): Flow<List<MyPokemon>>

    @Query("SELECT * FROM my_pokemon WHERE profile = :profile ORDER BY capturedAt DESC")
    fun getByProfile(profile: String): Flow<List<MyPokemon>>

    @Query("SELECT DISTINCT profile FROM my_pokemon ORDER BY profile")
    fun getProfiles(): Flow<List<String>>

    @Query("SELECT * FROM my_pokemon WHERE speciesId = :speciesId ORDER BY perfection DESC")
    fun getBySpecies(speciesId: String): Flow<List<MyPokemon>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(pokemon: MyPokemon): Long

    @Delete
    suspend fun delete(pokemon: MyPokemon)

    @Query("DELETE FROM my_pokemon WHERE id = :id")
    suspend fun deleteById(id: Long)

    @Update
    suspend fun update(pokemon: MyPokemon)
}
